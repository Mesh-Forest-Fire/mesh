import socket
import json
import time
import threading
import uuid
import sys

# Hardcoded node metadata
NODE_ID = "Relay_001" # ! We change this to a fixed ID for the respective Relay or Sentry node
NODE_LOCATION = {"lat": 49.2827, "lon": -123.1207}  # ! We set a fixed location for the Relay or Sentry node

BROADCAST_PORT = 5006
BROADCAST_ADDR = "10.0.0.255"   # uses interface broadcast. Note: we must co-ordinate addresses with the mesh setup scripts
TTL_DEFAULT = 8                 # max hops
SEEN_EXPIRY_SEC = 60            # how long to remember message IDs

seen_messages = {}              # msg_id -> timestamp
seen_lock = threading.Lock()

# If using Ethernet to connect to base station
# If we had an extra Linux machine, it could have been done more dynamically, but Windows had some technical problems,
#   so we fixed these manually
LAPTOP_IP = "fe80::7695:45d4:6de6:726e"  
LAPTOP_PORT = 6000
IFACE = "eth0"

def forward_to_laptop(msg_dict):
    try:
        s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        print("Laptop forward: created socket")
        scope_id = socket.if_nametoindex(IFACE) 
        print("Laptop forward: scope_id = ", scope_id)
        addr = (LAPTOP_IP, LAPTOP_PORT, 0, scope_id)
        print("Connecting to laptop at", (LAPTOP_IP, LAPTOP_PORT))
        s.connect(addr)
        print("Forwarding message to laptop:", msg_dict)
        s.sendall((json.dumps(msg_dict) + "\n").encode())
        print("Forwarded to laptop")
        s.close()
    except Exception as e:
        print("Laptop forward error:", e)



def now():
    return time.time()


def cleanup_seen_loop():
    """Periodically drop old message IDs so memory doesn't grow forever."""
    while True:
        cutoff = now() - SEEN_EXPIRY_SEC
        with seen_lock:
            old_keys = [mid for mid, ts in seen_messages.items() if ts < cutoff]
            for mid in old_keys:
                del seen_messages[mid]
        time.sleep(5)


def make_socket():
    """Create a UDP broadcast socket bound to all interfaces."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("", BROADCAST_PORT))
    return s


def new_message(payload, ttl=TTL_DEFAULT):
    """Create a new mesh message with unique ID and metadata."""
    return {
        "id": str(uuid.uuid4()),
        "src": NODE_ID,
        "src_location": NODE_LOCATION,
        "ttl": ttl,
        "ts": now(),
        "route": [NODE_ID],   # start route trace
        "payload": payload,
    }


def should_accept(msg_id):
    with seen_lock:
        if msg_id in seen_messages:
            return False
        seen_messages[msg_id] = now()
        return True


def send_raw(sock, msg_dict):
    data = json.dumps(msg_dict).encode("utf-8")
    sock.sendto(data, (BROADCAST_ADDR, BROADCAST_PORT))


def send_new(sock, payload, ttl=TTL_DEFAULT):
    """Entry point for app code: send a new message into the mesh."""
    msg = new_message(payload, ttl=ttl)
    print(f"[{NODE_ID}] sending new: {msg}")
    send_raw(sock, msg)


def handle_message(sock, msg_dict, addr):
    """Core mesh logic: accept, process, and possibly rebroadcast."""
    msg_id = msg_dict.get("id")
    src = msg_dict.get("src")
    ttl = msg_dict.get("ttl", 0)
    payload = msg_dict.get("payload")

    if not msg_id or src is None:
        return  # malformed

    # Loop prevention
    if not should_accept(msg_id):
        # print(f"[{NODE_ID}] duplicate {msg_id} from {addr}, ignoring")
        return

    # Don't rebroadcast if TTL exhausted
    if ttl <= 0:
        print(f"[{NODE_ID}] received (TTL=0) from {src}: {payload}")
        return

    # Application-level handling
    print(f"received from {src} via {addr}: {payload} route={msg_dict.get('route')}")

    # if isinstance(payload, dict) and payload.get("type") == "sensor":
    #     handle_sensor(payload)

    # Rebroadcast with decremented TTL
    fwd = dict(msg_dict)
    fwd["ttl"] = ttl - 1

    # Append this node to the route trace
    route = fwd.get("route", [])
    route = route + [NODE_ID]
    fwd["route"] = route

    print(f"[{NODE_ID}] rebroadcasting {msg_id} with TTL={fwd['ttl']} route={route}")
    send_raw(sock, fwd)
    
    try:
        forward_to_laptop(fwd)
    except Exception as e:
        print(f"[{NODE_ID}] error forwarding to laptop: {e}")



def listen_loop(sock):
    while True:
        try:
            data, addr = sock.recvfrom(4096)
            try:
                msg = json.loads(data.decode("utf-8"))
            except json.JSONDecodeError:
                print(f"[{NODE_ID}] non-JSON from {addr}: {data!r}")
                continue
            handle_message(sock, msg, addr)
        except Exception as e:
            print(f"[{NODE_ID}] error in listen_loop: {e}")
            time.sleep(0.5)


def main():
    global NODE_ID

    print(f"[{NODE_ID}] starting mesh node on UDP {BROADCAST_PORT}")
    sock = make_socket()

    t = threading.Thread(target=cleanup_seen_loop, daemon=True)
    t.start()

    if sys.argv[1:] and sys.argv[1] == "test-hello":
        send_new(sock, {"type": "hello", "msg": f"node {NODE_ID} online"})
        forward_to_laptop({
            "id": "test-hello-msg",
            "src": NODE_ID,
            "src_location": NODE_LOCATION,
            "ttl": TTL_DEFAULT,
            "ts": now(),
            "route": [NODE_ID],
            "payload": {"type": "hello", "msg": f"node {NODE_ID} online"},
        })

    if sys.argv[1:] and sys.argv[1] == "test-alert":
        # Full mock alert message with all fields
        mock_payload = {
            "type": "alert",
            "risk": 0.85,  # High risk value (0-1 scale)
            "sensor_data": {
                "temperature": 42.5,  # Celsius
                "humidity": 15.2,     # Percentage
                "air_quality": 180,   # AQI
                "light": 450          # Lux
            },
            "metadata": {}
        }
        forward_to_laptop({
            "id": "test-alert-msg",
            "src": NODE_ID,
            "src_location": NODE_LOCATION,
            "ttl": TTL_DEFAULT,
            "ts": now(),
            "route": [NODE_ID],
            "payload": mock_payload,
        })
        send_new(sock, mock_payload)
        

    # This listener is blocking
    listen_loop(sock)


if __name__ == "__main__":
    main()
