import socket
import json
import time
import threading
import uuid
import requests

# -------------------------------
# Base Station Metadata
# -------------------------------
NODE_ID = "BaseStation_001"
NODE_LOCATION = {"lat": 49.2827, "lon": -123.1207}

BROADCAST_PORT = 5006
BROADCAST_ADDR = "10.0.0.255"

SEEN_EXPIRY_SEC = 60
seen_messages = {}
seen_lock = threading.Lock()

API_GATEWAY_URL = "http://YOUR_API_GATEWAY/upload"   # <-- replace with real endpoint


# -------------------------------
# Utility
# -------------------------------
def now():
    return time.time()


def cleanup_seen_loop():
    """Periodically drop old message IDs."""
    while True:
        cutoff = now() - SEEN_EXPIRY_SEC
        with seen_lock:
            old = [mid for mid, ts in seen_messages.items() if ts < cutoff]
            for mid in old:
                del seen_messages[mid]
        time.sleep(5)


def make_socket():
    """Create a UDP listener socket."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("", BROADCAST_PORT))
    return s


def should_accept(msg_id):
    """Deduplication logic."""
    with seen_lock:
        if msg_id in seen_messages:
            return False
        seen_messages[msg_id] = now()
        return True


# -------------------------------
# Base Station Logic
# -------------------------------
def transform_for_gateway(msg_dict):
    """
    Convert mesh message into the format expected by your API gateway.
    Fill this in once your teammate defines the schema.
    """
    # Example placeholder transformation:
    return {
        "message_id": msg_dict.get("id"),
        "source": msg_dict.get("src"),
        "timestamp": msg_dict.get("ts"),
        "route": msg_dict.get("route"),
        "location": msg_dict.get("src_location"),
        "payload": msg_dict.get("payload"),
    }


def upload_to_gateway(transformed):
    """
    Upload transformed data to your MongoDB API gateway.
    """
    try:
        r = requests.post(API_GATEWAY_URL, json=transformed, timeout=3)
        print(f"[{NODE_ID}] uploaded to gateway: status={r.status_code}")
    except Exception as e:
        print(f"[{NODE_ID}] upload error: {e}")


def handle_message(msg_dict, addr):
    """Process incoming mesh messages (no rebroadcast)."""
    msg_id = msg_dict.get("id")
    src = msg_dict.get("src")
    payload = msg_dict.get("payload")

    if not msg_id or src is None:
        return

    if not should_accept(msg_id):
        return

    print(f"[{NODE_ID}] received from {src} via {addr}: {payload} route={msg_dict.get('route')}")

    # Transform and upload
    transformed = transform_for_gateway(msg_dict)
    upload_to_gateway(transformed)


def listen_loop(sock):
    while True:
        try:
            data, addr = sock.recvfrom(4096)
            try:
                msg = json.loads(data.decode("utf-8"))
            except json.JSONDecodeError:
                print(f"[{NODE_ID}] non-JSON from {addr}: {data!r}")
                continue

            handle_message(msg, addr)

        except Exception as e:
            print(f"[{NODE_ID}] error in listen_loop: {e}")
            time.sleep(0.5)


# -------------------------------
# Main
# -------------------------------
def main():
    print(f"[{NODE_ID}] starting base station listener on UDP {BROADCAST_PORT}")
    sock = make_socket()

    t = threading.Thread(target=cleanup_seen_loop, daemon=True)
    t.start()

    listen_loop(sock)


if __name__ == "__main__":
    main()
