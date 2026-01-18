import socket
import json
import os
import threading
from mongo_interface import *

# Connect to MongoDB at startup
mongodb_enabled = False
try:
    connect_mongodb()
    mongodb_enabled = True
    print("MongoDB connection established")
except Exception as e:
    print(f"Warning: MongoDB connection failed: {e}")
    print("Continuing without MongoDB...")

sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
sock.bind(("::", 6000))
sock.listen(1)

print("Listening on IPv6 port 6000")

BASE_NODE_ID = "Base_001"

def play_alert_sound():
    """Play an alert sound (platform-specific)."""
    try:
        if os.name == 'nt':  # Windows
            import winsound
            # Play system exclamation sound 3 times
            for _ in range(3):
                winsound.MessageBeep(winsound.MB_ICONHAND)
        else:  # Linux/Mac
            # Use system beep or play a sound file
            os.system('paplay /usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga 2>/dev/null || beep -f 1000 -l 500 || echo -e "\a"')
    except Exception as e:
        print(f"Could not play alert sound: {e}")

def show_red_screen():
    """Flash the terminal with red background."""
    try:
        # ANSI escape codes for red background
        RED_BG = "\033[41m"
        RESET = "\033[0m"
        CLEAR = "\033[2J\033[H"
        
        for _ in range(3):
            # Flash red
            print(f"{CLEAR}{RED_BG}" + " " * 80 + "\n" * 20 + "  🚨 FIRE ALERT DETECTED 🚨  ".center(80) + "\n" * 20 + RESET, end="", flush=True)
            import time
            time.sleep(0.3)
            # Clear
            print(CLEAR, end="", flush=True)
            time.sleep(0.2)
        
        # Final alert message
        print(f"{RED_BG}{'='*80}")
        print(f"  🔥 FIRE ALERT RECEIVED 🔥  ".center(80))
        print(f"{'='*80}{RESET}\n")
    except Exception as e:
        print(f"Could not show red screen: {e}")

def trigger_alerts():
    """Trigger both sound and visual alerts in a separate thread."""
    def alert_thread():
        show_red_screen()
        play_alert_sound()
    
    thread = threading.Thread(target=alert_thread, daemon=True)
    thread.start()

def handle_message(sock, msg, addr):
    print(f"Handling message from {addr}: {msg}")
    
    try:
        # Extract message components
        msg_id = msg.get("id")
        src_node = msg.get("src")
        src_location = msg.get("src_location", {})
        route = msg.get("route", [])
        payload = msg.get("payload", {})
        
        # Check if this is an alert message
        if payload.get("type") != "alert":
            print(f"Ignoring non-alert message type: {payload.get('type')}")
            return
        
        # ALERT DETECTED - Trigger visual and audio warnings
        trigger_alerts()
        
        sensor_data = payload.get("sensor_data", {})
        
        # Extract coordinates (lng, lat)
        lng = src_location.get("lon", 0)
        lat = src_location.get("lat", 0)
        
        # Message received means it passed threshold at source - mark as high severity
        # If risk score is available in payload, use it; otherwise default to 8
        risk_value = payload.get("risk")
        if isinstance(risk_value, (int, float)) and 0 <= risk_value <= 1:
            # Convert 0-1 risk to 1-10 severity scale
            severity = max(1, min(10, int(risk_value * 10)))
        else:
            # Alert passed threshold at source, so it's significant
            severity = 8
        
        # Create summary
        summary = f"Fire risk detected - Temp: {sensor_data.get('temperature', 'N/A')}°C, Humidity: {sensor_data.get('humidity', 'N/A')}%"
        
        # Only attempt MongoDB operations if available
        if not is_mongodb_available():
            print("⚠ MongoDB not available - incident not stored")
            return
        
        # Create incident in MongoDB
        incident_id = create_incident(
            incident_type="fire",
            severity=severity,
            origin_node_id=src_node,
            detection_method="sensor",
            coordinates=(lng, lat),
            region_code="BC-VAN",  # Could be made dynamic based on location
            base_node_id=BASE_NODE_ID,
            summary=summary,
            raw_data={
                "sensor_data": sensor_data,
                "message_id": msg_id,
                "timestamp": msg.get("ts")
            },
            incident_id=msg_id  # Use message ID as incident ID for idempotency
        )
        
        # Add traversal hops from the route
        for idx, node_id in enumerate(route):
            # Determine node type based on naming convention
            if "Sentry" in node_id or "Sensor" in node_id:
                node_type = "edge"
            elif "Relay" in node_id:
                node_type = "relay"
            elif "Base" in node_id:
                node_type = "base"
            else:
                node_type = "relay"  # default
            
            add_traversal_hop(
                incident_id=incident_id,
                node_id=node_id,
                node_type=node_type,
                protocol="radio",  # Assuming radio for mesh network
                encrypted=False,
                verified=True
            )
        
        # Update processing status
        update_base_receipt_status(incident_id, "completed")
        
        print(f"✓ Incident {incident_id} created and stored in MongoDB")
        
    except Exception as e:
        print(f"Error handling message: {e}")
        import traceback
        traceback.print_exc()

while True:
    conn, addr = sock.accept()
    conn.settimeout(5)  # Prevent hanging forever
    try:
        data = conn.recv(4096).decode()
        if data:
            msg = json.loads(data)
            print(f"Received from {addr}: {msg}")
            handle_message(sock, msg, addr)
        else:
            print(f"Connection from {addr} closed without data")
    except socket.timeout:
        print(f"Timeout from {addr}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()
