# client.py


import socket
import threading
import json
import time
import os
import shutil
from utils import send_msg, make_reply, now_iso, BufferedConnection # CHANGED

SERVER_ADDR = ("127.0.0.1", 5050)

class P2PClient:
    def __init__(self, name, p2p_port, repo_dir=None):
        self.log_callback = None
        self.name = name
        self.p2p_port = p2p_port
        self.repo_dir = repo_dir or f"./{name}_repo"
        os.makedirs(self.repo_dir, exist_ok=True)
        self.sock = None # Raw socket
        self.conn = None # BufferedConnection wrapper
        self.session_id = None
        self.cseq = 0
        self.lock = threading.Lock()
        self.heartbeat_interval = 30  # seconds
        self.heartbeat_thread = None
        self.running = False
        
        # Threading control for request/reply
        self.pending_replies = {} # cseq -> threading.Event
        self.reply_data = {}      # cseq -> dict
        self.recv_lock = threading.Lock() # Protects pending_replies and reply_data

    def next_cseq(self):
        with self.lock:
            self.cseq += 1
            return self.cseq
            
    def start_message_receiver(self):
        """
        Starts the *only* thread responsible for reading from the socket.
        It dispatches events and replies.
        """
        t = threading.Thread(target=self._message_receiver_loop, daemon=True)
        t.start()

    def log(self, *args, tag="default"):
        msg = " ".join(str(a) for a in args)
        ts = time.strftime("[%H:%M:%S]")
        if self.log_callback:
            # Pass the tag to the GUI
            self.log_callback(f"{ts} {msg}", tag)
        else:
            print(f"{ts} {msg}")

    def _message_receiver_loop(self):
        """
        The single message-processing loop.
        Reads all messages, routes events to log, and routes replies to waiting threads.
        """
        while self.running:
            try:
                msg = self.conn.recv_msg() # <--- CHANGED
                if not msg:
                    if self.running:
                        self.log("[SYSTEM] Connection closed by server.", tag="error")
                    break
                
                # Case 1: It's an event broadcast
                if "event" in msg:
                    ev = msg["event"]
                    if ev == "NEW_CLIENT":
                        self.log(f"[NETWORK] Peer '{msg['host']}' joined the network", tag="info")
                    elif ev == "PUBLISH":
                        files_str = ', '.join(msg['files'][:3])
                        if len(msg['files']) > 3:
                            files_str += f" (+{len(msg['files'])-3} more)"
                        self.log(f"[NETWORK] Peer '{msg['host']}' shared: {files_str}", tag="info")
                    elif ev == "LEAVE":
                        self.log(f"[NETWORK] Peer '{msg['host']}' left the network", tag="warning")
                
                # Case 2: It's a reply to one of our requests
                elif "cseq" in msg:
                    cseq = msg.get("cseq", 0)
                    with self.recv_lock:
                        if cseq in self.pending_replies:
                            self.reply_data[cseq] = msg
                            event = self.pending_replies.pop(cseq)
                            event.set() # Wake up the waiting thread
                        else:
                            # This can happen if a reply times out but arrives later
                            self.log(f"[SYSTEM] Received late/unexpected reply for cseq {cseq}", tag="warning")
                
                else:
                    self.log(f"[SYSTEM] Received unknown message: {msg}", tag="warning")

            except Exception as e:
                if self.running:
                    self.log(f"[SYSTEM] Message listener error: {e}", tag="error")
                break
        
        self.running = False
        self.log("[SYSTEM] Message listener stopped.", tag="info")
        # Clean up any waiting threads
        with self.recv_lock:
            for cseq, event in self.pending_replies.items():
                self.reply_data[cseq] = {"ok": False, "code": 0, "reason": "Connection closed"}
                event.set()
            self.pending_replies.clear()


    def connect_server(self):
        self.sock = socket.create_connection(SERVER_ADDR, timeout=3)
        self.conn = BufferedConnection(self.sock) # <--- WRAP IT
        
        # perform REGISTER
        req = {
            "type": "REGISTER",
            "cseq": self.next_cseq(),
            "host": {"name": self.name, "ip": self.sock.getsockname()[0], "p2p_port": self.p2p_port, "agent": "p2p/1.0"}
        }
        if not self.conn.send_msg(req): # <--- CHANGED
             raise ConnectionError("Failed to send REGISTER")
             
        reply = self.conn.recv_msg() # <--- CHANGED
        
        if reply and reply.get("ok"):
            self.session_id = reply.get("session_id")
            
            # ---!!! SỬA LỖI Ở ĐÂY !!!---
            self.sock.settimeout(None) # Xóa timeout để luồng nghe có thể block
            # --------------------------

            self.log(f"[CLIENT] Registered, session_id={self.session_id}", tag="success")
            self.running = True
            # start heartbeat
            self.heartbeat_thread = threading.Thread(target=self.heartbeat_loop, daemon=True)
            self.heartbeat_thread.start()
        else:
            self.log("[CLIENT] Register failed:", reply, tag="error")
            raise ConnectionError("Failed to register with server")

    def _send_request(self, req, timeout=5.0):
        """
        Helper function to send a request, wait for reply, and handle timeouts.
        """
        if not self.running or not self.conn:
            self.log("[SYSTEM] Not connected.", tag="error")
            return {"ok": False, "code": 0, "reason": "Not connected"}
        
        cseq = req["cseq"]
        event = threading.Event()
        
        with self.recv_lock:
            if cseq in self.pending_replies:
                self.log(f"[SYSTEM] CSEQ {cseq} already in use!", tag="error")
                return {"ok": False, "code": 0, "reason": "CSEQ conflict"}
            self.pending_replies[cseq] = event
            self.reply_data.pop(cseq, None) # Clear any old data
        
        try:
            if not self.conn.send_msg(req): # <--- CHANGED
                raise ConnectionError("Send failed")
        except Exception as e:
            self.log(f"[SYSTEM] Failed to send request: {e}", tag="error")
            with self.recv_lock:
                self.pending_replies.pop(cseq, None)
            return {"ok": False, "code": 0, "reason": "Send failed"}
        
        # Wait for the event to be set by the receiver thread
        if not event.wait(timeout=timeout):
            # Timeout
            self.log(f"[SYSTEM] Request {req['type']} (cseq {cseq}) timed out.", tag="error")
            with self.recv_lock:
                self.pending_replies.pop(cseq, None) # Remove from pending
            return {"ok": False, "code": 408, "reason": "Request timeout"}
        
        # Event was set, get data
        with self.recv_lock:
            reply = self.reply_data.pop(cseq, {"ok": False, "code": 0, "reason": "Reply data missing"})
        
        return reply


    def heartbeat_loop(self):
        while self.running:
            try:
                # Sleep for interval, but check self.running periodically
                for _ in range(self.heartbeat_interval):
                    if not self.running:
                        break
                    time.sleep(1)
                
                if not self.running:
                    break
                    
                req = {"type":"HEARTBEAT", "cseq": self.next_cseq(), "session_id": self.session_id, "load": 0}
                reply = self._send_request(req, timeout=5.0)
                
                if not reply or not reply.get("ok"):
                    self.log("[HEARTBEAT] No reply or error, will retry...", tag="warning")
                    if reply.get("code") == 404: # Session unknown
                        self.log("[HEARTBEAT] Session expired or unknown. Disconnecting.", tag="error")
                        self.running = False # Stop loops
                        
            except Exception as e:
                if self.running:
                    self.log(f"[HEARTBEAT] error: {e}", tag="error")
                break
        self.log("[SYSTEM] Heartbeat loop stopped.", tag="info")


    def publish(self, files_meta):
        """
        files_meta: list of dicts like {"fname":"a.txt","size":123,"hash": "..."}
        """
        if not self.session_id:
            self.log("[PUBLISH] Not registered.", tag="error")
            return
        if not files_meta:
            self.log("[PUBLISH] No files published.", tag="warning")
            return
            
        req = {"type":"PUBLISH", "cseq": self.next_cseq(), "session_id": self.session_id, "files": files_meta}
        reply = self._send_request(req)
        
        if reply and reply.get("ok"):
            self.log(f"[PUBLISH] Published {reply.get('accepted',0)} file(s)", tag="success")
        else:
            self.log(f"[PUBLISH] Failed: {reply}", tag="error")
        return reply

    def lookup(self, fname):
        req = {"type":"LOOKUP", "cseq": self.next_cseq(), "session_id": self.session_id, "fname": fname}
        reply = self._send_request(req)
        self.log(f"LOOKUP reply: {reply}", tag="info")
        return reply

    def discover(self, host):
        req = {"type":"DISCOVER", "cseq": self.next_cseq(), "session_id": self.session_id, "host": host}
        reply = self._send_request(req)
        self.log(f"DISCOVER reply: {reply}", tag="info")
        return reply

    def ping(self, host):
        req = {"type":"PING", "cseq": self.next_cseq(), "session_id": self.session_id, "host": host}
        reply = self._send_request(req)
        self.log(f"PING reply: {reply}", tag="info")
        return reply

    def leave(self):
        if not self.running:
            return
            
        self.running = False # Stop loops first
        
        req = {"type":"LEAVE", "cseq": self.next_cseq(), "session_id": self.session_id}
        reply = self._send_request(req, timeout=2.0)
        
        self.log(f"[LEAVE] Leaving server ({reply.get('code')})", tag="info")
        
        if self.conn:
            self.conn.close() # <--- CHANGED
        self.sock = None
        self.conn = None

    # ---- Data plane stub: uploader & downloader (simplified) ----
    # This part is unchanged as it uses its own sockets, not the control plane socket.
    
    def start_peer_listener(self):
        """
        Start a background thread to accept GET requests from other peers.
        The GET protocol described in spec (human readable start-line + headers)
        is kept minimal here: client receives "GET fname\r\n\r\n" and responds with file bytes.
        """
        t = threading.Thread(target=self._peer_server, daemon=True)
        t.start()

    def _peer_server(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(("0.0.0.0", self.p2p_port))
            s.listen()
            self.log(f"[PEER] listening for incoming GET on port {self.p2p_port}", tag="info")
        except Exception as e:
            self.log(f"[PEER] FATAL: Failed to bind to port {self.p2p_port}: {e}", tag="error")
            return
            
        while True:
            try:
                conn, addr = s.accept()
                threading.Thread(target=self._handle_peer_conn, args=(conn,addr), daemon=True).start()
            except Exception as e:
                self.log(f"[PEER] Error accepting connection: {e}", tag="error")


    def _handle_peer_conn(self, conn, addr):
        try:
            data = b""
            while b"\r\n\r\n" not in data:
                # Add timeout to peer connection
                conn.settimeout(10.0)
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
            
            if not data:
                return
                
            header = data.decode(errors="ignore")
            
            # Parse GET request: "GET filename\r\n\r\n"
            if header.startswith("GET"):
                lines = header.split("\r\n")
                if len(lines) > 0:
                    first_line = lines[0]
                    parts = first_line.split(None, 1)
                    
                    if len(parts) >= 2:
                        fname = parts[1].strip()
                        self.log(f"[PEER] Request for {fname} from {addr[0]}:{addr[1]}", tag="info")
                        
                        path = os.path.join(self.repo_dir, fname)
                        
                        if os.path.exists(path):
                            size = os.path.getsize(path)
                            # send simple OK response
                            resp_header = f"OK 200\r\nSize: {size}\r\n\r\n"
                            conn.sendall(resp_header.encode())
                            
                            # Send file content
                            with open(path, "rb") as f:
                                sent = 0
                                while True:
                                    chunk = f.read(8192)
                                    if not chunk:
                                        break
                                    conn.sendall(chunk)
                                    sent += len(chunk)
                            
                            self.log(f"[PEER] Served {fname} ({sent} bytes) to {addr[0]}:{addr[1]}", tag="success")
                        else:
                            conn.sendall(b"ERR 404 Not Found\r\n\r\n")
                            self.log(f"[PEER] File '{fname}' not found in {self.repo_dir}", tag="warning")
                            self.log(f"[PEER] Available files: {os.listdir(self.repo_dir)}", tag="info")
                    else:
                        conn.sendall(b"ERR 400 Bad Request\r\n\r\n")
                        self.log(f"[PEER] Malformed GET request from {addr[0]}:{addr[1]}", tag="error")
            else:
                conn.sendall(b"ERR 400 Bad Request\r\n\r\n")
                self.log(f"[PEER] Invalid request from {addr[0]}:{addr[1]}", tag="error")
                
        except socket.timeout:
            self.log(f"[PEER] Connection timed out from {addr[0]}:{addr[1]}", tag="warning")
        except Exception as e:
            self.log(f"[PEER] error serving: {e}", tag="error")
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
                        self.log("[FETCH] Connection closed by peer", tag="error")
                        return False
                    header += chunk
                
                header_text = header.decode(errors="ignore")
                
                # Check if response is an error
                if not header_text.startswith("OK"):
                    self.log(f"[FETCH] Peer returned error: {header_text.strip()}", tag="error")
                    return False
                
                # Parse size
                size_line = [line for line in header_text.split("\r\n") if line.lower().startswith("size:")]
                if not size_line:
                    self.log("[FETCH] Invalid response: missing Size header", tag="error")
                    return False
                    
                size = int(size_line[0].split(":")[1].strip())
                
                # The rest of header buffer after \r\n\r\n may contain file data
                parts = header.split(b"\r\n\r\n", 1)
                data_start = parts[1] if len(parts) > 1 else b""
                
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
                
                if received < size:
                    self.log(f"[FETCH] Incomplete download: {received}/{size} bytes", tag="warning")
                    os.remove(path) # Clean up partial file
                    return False
                    
                self.log(f"[FETCH] Downloaded {fname} ({received} bytes) from {ip}:{port}", tag="success")
                return True
                
        except socket.timeout:
            self.log(f"[FETCH] Connection timeout to {ip}:{port}", tag="error")
            return False
        except ConnectionRefusedError:
            self.log(f"[FETCH] Connection refused by {ip}:{port}", tag="error")
            return False
        except Exception as e:
            self.log(f"[FETCH] error: {e}", tag="error")
            return False

def cli_demo():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--p2p-port", type=int, default=6000)
    args = parser.parse_args()

    client = P2PClient(args.name, args.p2p_port)
    client.start_peer_listener()
    
    try:
        client.connect_server()
        client.start_message_receiver() # Start receiver for CLI mode
    except ConnectionError as e:
        print(f"Failed to connect to server: {e}. Exiting.")
        return

    print("Enter commands: publish <fname>, lookup <fname>, discover <host>, ping <host>, leave, exit")
    while client.running:
        try:
            line = input(">> ").strip()
        except EOFError:
            client.leave()
            break
        if not line:
            continue
        parts = line.split()
        if not parts:
            continue
        cmd = parts[0].lower()
        if cmd == "publish" and len(parts) >= 2:
            fname = parts[1]
            path = os.path.join(client.repo_dir, fname)
            if os.path.exists(path):
                meta = {"fname": fname, "size": os.path.getsize(path)}
                client.publish([meta])
            else:
                print("File not found in repo. Put file in", client.repo_dir)
        elif cmd == "lookup" and len(parts) == 2:
            fname = parts[1]
            reply = client.lookup(fname)
            peers = reply.get("peers", [])
            if peers:
                print(f"[LOOKUP] Found {len(peers)} peer(s):")
                for i, p in enumerate(peers, 1):
                    print(f"  {i}. {p['host']} ({p['ip']}:{p['p2p_port']}) size={p.get('size')}")
                
                choice = input("Download from first peer? (y/n): ").strip().lower()
                if choice == "y":
                    first_peer = peers[0]
                    client.fetch_from_peer(first_peer["ip"], first_peer["p2p_port"], fname)
            else:
                print("[LOOKUP] No peers found for this file.")
        elif cmd == "discover" and len(parts) == 2:
            client.discover(parts[1])
        elif cmd == "ping" and len(parts) == 2:
            client.ping(parts[1])
        elif cmd == "leave":
            client.leave()
        elif cmd == "exit":
            client.leave()
            break
        else:
            print("Unknown command")

    print("Exiting...")

    
if __name__ == "__main__":
    cli_demo()