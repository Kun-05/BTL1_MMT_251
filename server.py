import socket
import threading
from utils import send_msg, recv_msg

def handle_client(conn, addr):
    # Xử lý từng client tại đây
    pass

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind(('0.0.0.0', 5000))
server.listen()
print("Server listening on port 5000...")

while True:
    conn, addr = server.accept()
    threading.Thread(target=handle_client, args=(conn, addr)).start()
