import json
from datetime import datetime, timezone
import socket

CRLF = "\r\n"

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def send_msg(sock, obj):
    """
    Send a JSON-line message over a connected socket.
    Appends CRLF and flushes. sock.sendall expects bytes.
    Returns True on success, False on failure.
    """
    try:
        raw = json.dumps(obj, ensure_ascii=False) + CRLF
        sock.sendall(raw.encode("utf-8"))
        return True
    except Exception:
        return False # Send failed

def make_reply(req, type_name, ok=True, code=200, extra=None):
    """
    Build a reply envelope from a request obj (if present).
    - req may be None: you can pass cseq/session_id manually in extra.
    """
    base = {
        "type": type_name,
        "cseq": req.get("cseq") if req else 0,
        "ok": ok,
        "code": code,
        "time": now_iso()
    }
    if extra:
        base.update(extra)
    return base

class BufferedConnection:
    """
    A wrapper around a socket that handles buffered reading of JSON-line messages.
    """
    def __init__(self, sock):
        self.sock = sock
        self.buffer = b""

    def recv_msg(self, bufsize=4096):
        """
        Receive one JSON-line message, using the internal buffer.
        Returns Python object (dict) or None if connection closed or JSON is bad.
        """
        while CRLF.encode() not in self.buffer:
            try:
                chunk = self.sock.recv(bufsize)
                if not chunk:
                    return None  # Connection closed
                self.buffer += chunk
            except (OSError, socket.timeout, ConnectionError):
                return None # Connection error
        
        line, _, rest = self.buffer.partition(CRLF.encode())
        self.buffer = rest  # CRITICAL: Keep the rest for next call
        
        try:
            obj = json.loads(line.decode("utf-8"))
        except Exception as e:
            print(f"[BufferedConnection] Failed to decode JSON: {line} ({e})")
            return None # Bad JSON
        return obj

    def send_msg(self, obj):
        """Helper to send a message on this connection's socket."""
        return send_msg(self.sock, obj)

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass