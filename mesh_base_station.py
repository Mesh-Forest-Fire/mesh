import socket
import json

sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
sock.bind(("::", 6000))
sock.listen(1)

print("Listening on IPv6 port 6000")

while True:
    conn, addr = sock.accept()
    conn.settimeout(5)  # Prevent hanging forever
    try:
        data = conn.recv(4096).decode()
        if data:
            msg = json.loads(data)
            print(f"Received from {addr}: {msg}")
        else:
            print(f"Connection from {addr} closed without data")
    except socket.timeout:
        print(f"Timeout from {addr}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()
