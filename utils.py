# protocol.py
# Helper functions for JSON Lines control protocol (C <-> S).
# Messages are JSON objects, encoded in UTF-8, terminated by "\r\n".

import json
from datetime import datetime, timezone

CRLF = "\r\n"

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def send_msg(sock, obj):
    """
    Send a JSON-line message over a connected socket.
    Appends CRLF and flushes. sock.sendall expects bytes.
    """
    raw = json.dumps(obj, ensure_ascii=False) + CRLF
    sock.sendall(raw.encode("utf-8"))

def recv_msg(sock, bufsize=4096):
    """
    Receive one JSON-line message.
    This simple helper reads until it sees CRLF.
    Note: blocking read; for production use a buffered reader.
    Returns Python object (dict) or None if connection closed.
    """
    data = b""
    while True:
        chunk = sock.recv(bufsize)
        if not chunk:
            return None
        data += chunk
        if CRLF.encode() in data:
            line, _, rest = data.partition(CRLF.encode())
            try:
                obj = json.loads(line.decode("utf-8"))
            except Exception:
                return None
            return obj

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
