def send_msg(sock, msg):
    sock.sendall((msg + "\n").encode())

def recv_msg(sock):
    return sock.recv(1024).decode().strip()
