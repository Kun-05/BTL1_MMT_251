# client.py
# Simple client skeleton for control-plane operations (REGISTER, PUBLISH, LOOKUP, DISCOVER, PING, HEARTBEAT, LEAVE).
# CLI for testing. Data-plane (GET file) is provided as a simple stub to be extended.

import socket
import threading
import json
import time
import os
from utils import send_msg, recv_msg, make_reply, now_iso

SERVER_ADDR = ("127.0.0.1", 5050)

class P2PClient:
    def __init__(self, name, p2p_port, repo_dir=None):
        self.log_callback = None
        self.name = name
        self.p2p_port = p2p_port
        self.repo_dir = repo_dir or f"./{name}_repo"
        os.makedirs(self.repo_dir, exist_ok=True)
        self.sock = None
        self.session_id = None
        self.cseq = 0
        self.lock = threading.Lock()
        self.heartbeat_interval = 30  # seconds
        self.heartbeat_thread = None
        self.running = False

    def next_cseq(self):
        with self.lock:
            self.cseq += 1
            return self.cseq
    def start_listen_events(self):
        t = threading.Thread(target=self._listen_events, daemon=True)
        t.start()

    def log(self, *args):
        msg = " ".join(str(a) for a in args)
        ts = time.strftime("[%H:%M:%S]")
        if self.log_callback:
            self.log_callback(f"{ts} {msg}")
        else:
            print(f"{ts} {msg}")



    def _listen_events(self):
        while self.running:
            try:
                evt = recv_msg(self.sock)
                if not evt:
                    break
                if "event" in evt:
                    ev = evt["event"]
                    if ev == "NEW_CLIENT":
                        self.log(f"[EVENT] New client joined: {evt['host']}")
                    elif ev == "PUBLISH":
                        self.log(f"[EVENT] {evt['host']} published files: {evt['files']}")
                    elif ev == "LEAVE":
                        self.log(f"[EVENT] {evt['host']} has left the server.")
                    else:
                        self.log(f"[EVENT] {evt}")

            except Exception as e:
                break

    def connect_server(self):
        self.sock = socket.create_connection(SERVER_ADDR, timeout=3)
        # perform REGISTER
        req = {
            "type": "REGISTER",
            "cseq": self.next_cseq(),
            "host": {"name": self.name, "ip": self.sock.getsockname()[0], "p2p_port": self.p2p_port, "agent": "p2p/1.0"}
        }
        send_msg(self.sock, req)
        reply = recv_msg(self.sock)
        if reply and reply.get("ok"):
            self.session_id = reply.get("session_id")
            self.log(f"[CLIENT] Registered, session_id={self.session_id}")
            self.running = True
            # start heartbeat
            self.heartbeat_thread = threading.Thread(target=self.heartbeat_loop, daemon=True)
            self.heartbeat_thread.start()
        else:
            self.log("[CLIENT] Register failed:", reply)

    def heartbeat_loop(self):
        while self.running:
            try:
                time.sleep(self.heartbeat_interval)
                if not self.sock:
                    continue
                req = {"type":"HEARTBEAT", "cseq": self.next_cseq(), "session_id": self.session_id, "load": 0}
                send_msg(self.sock, req)
                reply = recv_msg(self.sock)
                if not reply or not reply.get("ok"):
                    self.log("[HEARTBEAT] No reply, will retry...")
            except (OSError, ConnectionError):
                self.log("[HEARTBEAT] Lost connection to server.")
                break
            except Exception as e:
                self.log("[HEARTBEAT] error:", e)


    def publish(self, files_meta):
        """
        files_meta: list of dicts like {"fname":"a.txt","size":123,"hash": "..."}
        """
        if not self.session_id:
            self.log("[PUBLISH] Not registered.")
            return
        if not files_meta:
            self.log("[PUBLISH] No files published.")
            return
        req = {"type":"PUBLISH", "cseq": self.next_cseq(), "session_id": self.session_id, "files": files_meta}
        send_msg(self.sock, req)
        reply = recv_msg(self.sock)
        if reply and reply.get("ok"):
            self.log(f"[PUBLISH] Published {reply.get('accepted',0)} file(s)")
        else:
            self.log("[PUBLISH] Failed:", reply)
        return reply

    def lookup(self, fname):
        req = {"type":"LOOKUP", "cseq": self.next_cseq(), "session_id": self.session_id, "fname": fname}
        send_msg(self.sock, req)
        reply = recv_msg(self.sock)
        self.log("LOOKUP reply:", reply)
        return reply

    def discover(self, host):
        req = {"type":"DISCOVER", "cseq": self.next_cseq(), "session_id": self.session_id, "host": host}
        send_msg(self.sock, req)
        reply = recv_msg(self.sock)
        self.log("DISCOVER reply:", reply)
        return reply

    def ping(self, host):
        req = {"type":"PING", "cseq": self.next_cseq(), "session_id": self.session_id, "host": host}
        send_msg(self.sock, req)
        reply = recv_msg(self.sock)
        self.log("PING reply:", reply)
        return reply

    def leave(self):
        req = {"type":"LEAVE", "cseq": self.next_cseq(), "session_id": self.session_id}
        send_msg(self.sock, req)
        reply = recv_msg(self.sock)
        self.log(f"[LEAVE] Leaving server ({reply.get('code')})")
        self.running = False
        try:
            self.sock.close()
        except:
            pass

    # ---- Data plane stub: uploader & downloader (simplified) ----
    def start_peer_listener(self):
        """
        Start a background thread to accept GET requests from other peers.
        The GET protocol described in spec (human readable start-line + headers)
        is kept minimal here: client receives "GET fname\r\n\r\n" and responds with file bytes.
        """
        t = threading.Thread(target=self._peer_server, daemon=True)
        t.start()

    def _peer_server(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("0.0.0.0", self.p2p_port))
        s.listen()
        self.log(f"[PEER] listening for incoming GET on port {self.p2p_port}")
        while True:
            conn, addr = s.accept()
            threading.Thread(target=self._handle_peer_conn, args=(conn,addr), daemon=True).start()

    def _handle_peer_conn(self, conn, addr):
        try:
            data = b""
            while b"\r\n\r\n" not in data:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
            header = data.decode(errors="ignore")
            # Very small parser:
            if header.startswith("GET"):
                _, fname = header.split(None, 1)[1].split("\r\n",1)[0].split(None,1)
                path = os.path.join(self.repo_dir, fname)
                if os.path.exists(path):
                    size = os.path.getsize(path)
                    # send simple OK response
                    resp_header = f"OK 200\r\nSize: {size}\r\n\r\n"
                    conn.sendall(resp_header.encode())
                    with open(path, "rb") as f:
                        while True:
                            chunk = f.read(8192)
                            if not chunk:
                                break
                            conn.sendall(chunk)
                else:
                    conn.sendall(b"ERR 404 Not Found\r\n\r\n")
        except Exception as e:
            self.log("[PEER] error serving:", e)
        finally:
            try:
                conn.close()
            except:
                pass
    def fetch_from_peer(self, ip, port, fname, save_as=None):
            """
            Download file 'fname' from given peer (ip, port)
            """
            save_as = save_as or fname
            path = os.path.join(self.repo_dir, save_as)
            try:
                with socket.create_connection((ip, port), timeout=5) as s:
                    req = f"GET {fname}\r\n\r\n".encode()
                    s.sendall(req)
                    header = b""
                    while b"\r\n\r\n" not in header:
                        chunk = s.recv(1024)
                        if not chunk:
                            return False
                        header += chunk
                    header_text = header.decode(errors="ignore")
                    if not header_text.startswith("OK"):
                        self.log("[FETCH] Peer returned error:", header_text.strip())
                        return False
                    # Parse size
                    size_line = [line for line in header_text.split("\r\n") if line.lower().startswith("size:")]
                    size = int(size_line[0].split(":")[1].strip()) if size_line else 0
                    # The rest of header buffer after \r\n\r\n may contain file data
                    data_start = header.split(b"\r\n\r\n", 1)[1]
                    with open(path, "wb") as f:
                        if data_start:
                            f.write(data_start)
                        received = len(data_start)
                        while received < size:
                            chunk = s.recv(8192)
                            if not chunk:
                                break
                            f.write(chunk)
                            received += len(chunk)
                    self.log(f"[FETCH] Downloaded {fname} ({received} bytes) from {ip}:{port}")
                    return True
            except Exception as e:
                self.log("[FETCH] error:", e)
                return False

def cli_demo():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--p2p-port", type=int, default=6000)
    args = parser.parse_args()

    client = P2PClient(args.name, args.p2p_port)
    client.start_peer_listener()
    client.connect_server()

    self.log("Enter commands: publish <fname>, lookup <fname>, discover <host>, ping <host>, leave, exit")
    while True:
        try:
            line = input(">> ").strip()
        except EOFError:
            break
        if not line:
            continue
        parts = line.split()
        cmd = parts[0].lower()
        if cmd == "publish" and len(parts) >= 2:
            fname = parts[1]
            path = os.path.join(client.repo_dir, fname)
            if os.path.exists(path):
                meta = {"fname": fname, "size": os.path.getsize(path)}
                client.publish([meta])
            else:
                self.log("File not found in repo. Put file in", client.repo_dir)
        elif cmd == "lookup" and len(parts) == 2:
            fname = parts[1]
            reply = client.lookup(fname)
            peers = reply.get("peers", [])
            if peers:
                self.log(f"[LOOKUP] Found {len(peers)} peer(s):")
                for i, p in enumerate(peers, 1):
                    self.log(f"  {i}. {p['host']} ({p['ip']}:{p['p2p_port']}) size={p.get('size')}")
                
                choice = input("Download from first peer? (y/n): ").strip().lower()
                if choice == "y":
                    first_peer = peers[0]
                    client.fetch_from_peer(first_peer["ip"], first_peer["p2p_port"], fname)
            else:
                self.log("[LOOKUP] No peers found for this file.")
        elif cmd == "discover" and len(parts) == 2:
            client.discover(parts[1])
        elif cmd == "ping" and len(parts) == 2:
            client.ping(parts[1])
        elif cmd == "leave":
            client.leave()
        elif cmd == "exit":
            try:
                client.leave()
            except:
                pass
            break
        else:
            self.log("Unknown command")

    
if __name__ == "__main__":
    cli_demo()
