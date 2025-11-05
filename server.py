# server.py
# Index server implementing REGISTER, PUBLISH, LOOKUP, DISCOVER, PING, LEAVE, HEARTBEAT.
# Control plane uses JSON Lines over TCP.

import socket
import threading
import json
import time
import itertools
from utils import recv_msg, send_msg, make_reply, now_iso

SERVER_HOST = "0.0.0.0"
SERVER_PORT = 5050



# In-memory stores
sessions_lock = threading.Lock()
_next_session = itertools.count(1)
sessions = {}   # session_id -> {host, ip, p2p_port, last_seen, ttl}
hosts = {}      # hostname -> session_id
index_lock = threading.Lock()
file_index = {}  # fname -> { host -> { size, hash, last_seen } }

# Config
DEFAULT_TTL = 60  # seconds
CLEANUP_INTERVAL = 10  # seconds

#Global variables
client_conn = set()
conn_lock = threading.Lock()

def broadcast_event(event_obj):
    """Send a JSON event to all connected clients."""
    global client_conn, conn_lock
    with conn_lock:
        dead = []
        for c in list(client_conn):
            try:
                send_msg(c, event_obj)
            except:
                dead.append(c)
        for d in dead:
            client_conn.discard(d)

def cleanup_stale_sessions():
    while True:
        now = time.time()
        to_remove = []
        with sessions_lock:
            for sid, info in list(sessions.items()):
                if info.get("expiry", 0) < now:
                    to_remove.append((sid, info["host"]))
            for sid, host in to_remove:
                sessions.pop(sid, None)
                hosts.pop(host, None)
                # remove host from file_index
                with index_lock:
                    for fname, owners in list(file_index.items()):
                        if host in owners:
                            owners.pop(host, None)
                            if not owners:
                                file_index.pop(fname, None)
                print(f"[CLEANUP] removed expired session {sid} ({host})")
        time.sleep(CLEANUP_INTERVAL)

def handle_connection(conn, addr):
    """
    Each client connection handles control-plane JSON requests synchronously.
    """
    global client_conn, conn_lock
    try:
        with conn_lock:
            client_conn.add(conn)
        while True:
            req = recv_msg(conn)
            if req is None:
                break
            req_type = req.get("type", "").upper()
            cseq = req.get("cseq", 0)
            # REGISTER
            if req_type == "REGISTER":
                host_info = req.get("host", {})
                name = host_info.get("name")
                ip = host_info.get("ip", addr[0])
                p2p_port = host_info.get("p2p_port")
                if not name or not p2p_port:
                    reply = make_reply(req, "REGISTER-ERROR", ok=False, code=400, extra={"reason":"missing fields"})
                    send_msg(conn, reply)
                    continue
                with sessions_lock:
                    sid = next(_next_session)
                    expiry = time.time() + DEFAULT_TTL
                    sessions[sid] = {"host":name, "ip":ip, "p2p_port":p2p_port, "last_seen": now_iso(), "expiry": expiry, "ttl": DEFAULT_TTL}
                    hosts[name] = sid
                reply = make_reply(req, "REGISTER-OK", ok=True, code=200, extra={"session_id": sid, "ttl": DEFAULT_TTL})
                send_msg(conn, reply)
                print(f"[REGISTER] {name} @ {ip}:{p2p_port} sid={sid}")
                broadcast_event({
                    "event": "NEW_CLIENT",
                    "host": name,
                    "ip": ip,
                    "p2p_port": p2p_port,
                    "time": now_iso()
                })
            # PUBLISH
            elif req_type == "PUBLISH":
                sid = req.get("session_id")
                files = req.get("files", [])
                with sessions_lock:
                    session = sessions.get(sid)
                if not session:
                    send_msg(conn, make_reply(req, "PUBLISH-ERROR", ok=False, code=401, extra={"reason":"unknown session"}))
                    continue
                hostname = session["host"]
                updated = 0
                with index_lock:
                    for f in files:
                        fname = f.get("fname")
                        size = f.get("size")
                        hsh = f.get("hash")
                        if not fname:
                            continue
                        if fname not in file_index:
                            file_index[fname] = {}
                        file_index[fname][hostname] = {"size": size, "hash": hsh, "last_seen": now_iso()}
                        updated += 1
                send_msg(conn, make_reply(req, "PUBLISH-OK", ok=True, code=200, extra={"accepted": updated}))
                print(f"[PUBLISH] {hostname} published {updated} files")
                broadcast_event({
                "event": "PUBLISH",
                "host": hostname,
                "files": [f.get("fname") for f in files],
                "time": now_iso()
                })

            # LOOKUP
            elif req_type == "LOOKUP":
                sid = req.get("session_id")
                fname = req.get("fname")
                with sessions_lock:
                    if sid not in sessions:
                        send_msg(conn, make_reply(req, "LOOKUP-ERROR", ok=False, code=401, extra={"reason":"unknown session"}))
                        continue
                with index_lock:
                    owners = file_index.get(fname, {})
                    peers = []
                    for host, meta in owners.items():
                        sid_of_host = hosts.get(host)
                        session = sessions.get(sid_of_host) if sid_of_host else None
                        if session:
                            peers.append({"host": host, "ip": session["ip"], "p2p_port": session["p2p_port"], "size": meta.get("size"), "hash": meta.get("hash")})
                send_msg(conn, make_reply(req, "LOOKUP-OK", ok=True, code=200, extra={"peers": peers}))

            # DISCOVER
            elif req_type == "DISCOVER":
                target = req.get("host")
                sid_of_target = hosts.get(target)
                files_list = []
                with index_lock:
                    if sid_of_target:
                        for fname, owners in file_index.items():
                            meta = owners.get(target)
                            if meta:
                                files_list.append({"fname": fname, "size": meta.get("size"), "hash": meta.get("hash"), "last_seen": meta.get("last_seen")})
                send_msg(conn, make_reply(req, "DISCOVER-OK", ok=True, code=200, extra={"files": files_list}))

            # PING
            elif req_type == "PING":
                target = req.get("host")
                sid_of_target = hosts.get(target)
                if not sid_of_target:
                    send_msg(conn, make_reply(req, "PING-OK", ok=True, code=404, extra={"alive": False}))
                else:
                    sess = sessions.get(sid_of_target)
                    send_msg(conn, make_reply(req, "PING-OK", ok=True, code=200, extra={"alive": True, "ip": sess["ip"], "p2p_port": sess["p2p_port"], "last_seen": sess["last_seen"]}))

            # HEARTBEAT
            elif req_type == "HEARTBEAT":
                sid = req.get("session_id")
                load = req.get("load")
                with sessions_lock:
                    if sid in sessions:
                        sessions[sid]["last_seen"] = now_iso()
                        sessions[sid]["expiry"] = time.time() + sessions[sid]["ttl"]
                        sessions[sid]["load"] = load
                        send_msg(conn, make_reply(req, "HEARTBEAT-OK", ok=True, code=200, extra={"ttl": sessions[sid]["ttl"]}))
                    else:
                        send_msg(conn, make_reply(req, "HEARTBEAT-ERROR", ok=False, code=401, extra={"reason":"unknown session"}))

            # LEAVE
            elif req_type == "LEAVE":
                sid = req.get("session_id")
                with sessions_lock:
                    sess = sessions.pop(sid, None)
                    if sess:
                        hosts.pop(sess["host"], None)
                        # remove host entries from index
                        with index_lock:
                            for fname, owners in list(file_index.items()):
                                owners.pop(sess["host"], None)
                                if not owners:
                                    file_index.pop(fname, None)
                        send_msg(conn, make_reply(req, "LEAVE-OK", ok=True, code=200))
                        print(f"[LEAVE] {sess['host']} left")
                        broadcast_event({
    "event": "LEAVE",
    "host": sess["host"],
    "time": now_iso()
})

                    else:
                        send_msg(conn, make_reply(req, "LEAVE-ERROR", ok=False, code=401, extra={"reason":"unknown session"}))

            else:
                send_msg(conn, make_reply(req, "ERROR", ok=False, code=400, extra={"reason":"unsupported type"}))
    except Exception as e:
        print("[SERVER] connection handler error:", e)
    finally:
        with conn_lock:
            client_conn.discard(conn)
        try:
            conn.close()
        except:
            pass

def start_server(host=SERVER_HOST, port=SERVER_PORT):
    # spawn cleanup thread
    t = threading.Thread(target=cleanup_stale_sessions, daemon=True)
    t.start()

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((host, port))
    s.listen()
    print(f"[SERVER] Listening on {host}:{port}")
    try:
        while True:
            conn, addr = s.accept()
            threading.Thread(target=handle_connection, args=(conn, addr), daemon=True).start()
    except KeyboardInterrupt:
        print("Server shutting down")
    finally:
        s.close()

if __name__ == "__main__":
    start_server()
