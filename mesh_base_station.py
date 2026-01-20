import socket
import json
import threading
import os
import time
import requests
import logging
from datetime import datetime, timezone

# Configure logger
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# API Gateway configuration
API_GATEWAY_URL = "https://api-gateway-production-df4f.up.railway.app/api"
API_TIMEOUT = 10  # seconds

# Alert deduplication configuration
ALERT_COOLDOWN_SECONDS = 60  # Don't re-alert from same source within this period

# Track last alert time per source node
last_alert_times = {}  # node_id -> timestamp
alert_lock = threading.Lock()

sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
sock.bind(("::", 6000))
sock.listen(1)

print("Listening on IPv6 port 6000")

BASE_NODE_ID = "Base_001"

def should_alert(node_id: str) -> bool:
    """
    Check if we should trigger alerts for this node.
    Returns True if enough time has passed since last alert from this source.
    """
    with alert_lock:
        now = time.time()
        last_alert = last_alert_times.get(node_id)
        
        if last_alert is None:
            # First alert from this node
            last_alert_times[node_id] = now
            return True
        
        time_since_last = now - last_alert
        
        if time_since_last >= ALERT_COOLDOWN_SECONDS:
            # Cooldown period has passed
            last_alert_times[node_id] = now
            return True
        
        # Still in cooldown
        logger.info(f"⏱️  Suppressing alert from {node_id} (cooldown: {time_since_last:.1f}s / {ALERT_COOLDOWN_SECONDS}s)")
        return False

def play_alert_sound():
    """Play an alert sound (platform-specific)."""
    try:
        if os.name == 'nt':
            import winsound
            for _ in range(3):
                winsound.MessageBeep(winsound.MB_ICONHAND)
                time.sleep(0.3)
        else:
            os.system('paplay /usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga 2>/dev/null || beep')
    except Exception as e:
        logger.error(f"Could not play alert sound: {e}")

def show_red_screen():
    """Flash the terminal with red background."""
    try:
        RED_BG = "\033[41m"
        RESET = "\033[0m"
        CLEAR = "\033[2J\033[H"
        
        for _ in range(3):
            print(f"{CLEAR}{RED_BG}{' ' * 80}\n{' ' * 80}\n{'  🚨 FIRE ALERT DETECTED 🚨  '.center(80)}\n{' ' * 80}\n{' ' * 80}{RESET}")
            time.sleep(0.3)
        
        print(f"{RED_BG}{'='*80}")
        print(f"  🔥 FIRE ALERT RECEIVED 🔥  ".center(80))
        print(f"{'='*80}{RESET}\n")
    except Exception as e:
        logger.error(f"Could not show red screen: {e}")

def format_iso_timestamp(dt):
    """Format datetime as ISO 8601 with milliseconds (3 decimals) and Z suffix."""
    return dt.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

def trigger_alerts():
    """Trigger both sound and visual alerts in a separate thread."""
    def alert_thread():
        show_red_screen()
        play_alert_sound()
    
    thread = threading.Thread(target=alert_thread, daemon=True)
    thread.start()

def submit_incident_to_api(incident_data: dict) -> bool:
    """Submit incident to API Gateway."""
    try:
        url = f"{API_GATEWAY_URL}/incidents"
        logger.info(f"🌐 Submitting incident to API Gateway: {url}")
        payload_str = json.dumps(incident_data, indent=2)
        logger.info(f"📋 Incident payload:\n{payload_str}")
        
        response = requests.post(
            url,
            json=incident_data,
            timeout=API_TIMEOUT,
            headers={"Content-Type": "application/json"}
        )
        
        logger.info(f"📡 API Response Status: {response.status_code}")
        
        if response.status_code == 201:
            try:
                resp_json = response.json()
                logger.info(f"✅ Incident submitted successfully: {resp_json.get('incidentId')}")
            except:
                logger.info(f"✅ Incident submitted successfully")
            return True
        else:
            logger.warning(f"⚠ API returned non-201 status: {response.status_code}")
            logger.warning(f"📥 Full API Response:\n{response.text}")
            # Try to parse JSON error if available
            try:
                error_json = response.json()
                logger.warning(f"📥 API Error JSON: {json.dumps(error_json, indent=2)}")
            except:
                pass
            return False
            
    except requests.exceptions.Timeout:
        logger.error(f"❌ API request timed out after {API_TIMEOUT}s")
        return False
    except requests.exceptions.ConnectionError as e:
        logger.error(f"❌ Could not connect to API Gateway: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Error submitting to API: {e}", exc_info=True)
        return False

def handle_message(sock, msg, addr):
    logger.info(f"Handling message from {addr}: {msg}")
    
    try:
        msg_id = msg.get("id")
        payload = msg.get("payload", {})
        msg_type = payload.get("type")
        
        if msg_type != "alert":
            logger.debug(f"Ignoring non-alert message type: {msg_type}")
            return
        
        # Extract source node
        src_node = msg.get("src", "unknown")
        
        logger.info(f"🔥 ALERT MESSAGE RECEIVED - ID: {msg_id} from {src_node}")
        
        # Check if we should trigger alerts (cooldown check)
        if should_alert(src_node):
            # Trigger visual and audio alerts
            trigger_alerts()
        else:
            logger.info(f"📵 Alert suppressed due to cooldown")
        
        # Extract data from message (always submit to API regardless of alert status)
        src_location = msg.get("src_location", {})
        route = msg.get("route", [])
        sensor_data = payload.get("sensor_data", {})
        risk = payload.get("risk", 0.8)
        
        # Convert risk (0-1) to severity (1-10)
        severity = max(1, min(10, int(risk * 10)))
        
        # Build incident data matching API schema
        incident_data = {
            "incidentId": msg_id,
            "type": "fire",
            "severity": severity,
            "status": "open",
            "source": {
                "originNodeId": src_node,
                "detectionMethod": "sensor",
                "detectedAt": format_iso_timestamp(datetime.now(timezone.utc))
            },
            "location": {
                "coordinates": [
                    src_location.get("lon", 0),
                    src_location.get("lat", 0)
                ],
                "regionCode": "UNKNOWN",  # Could extract from NODE_ID or add to mesh protocol
                "description": f"Alert from {src_node}"
            },
            "traversalPath": [
                {
                    "hopIndex": idx,
                    "nodeId": node_id
                }
                for idx, node_id in enumerate(route)
            ],
            "baseReceipt": {
                "baseNodeId": BASE_NODE_ID,
                "receivedAt": format_iso_timestamp(datetime.now(timezone.utc)),
                "processingStatus": "queued"
            },
            "payload": {
                "summary": f"Fire risk detected: {risk:.2%} probability",
                "raw": {
                    "risk": risk,
                    "sensor_data": sensor_data
                }
            }
        }
        
        logger.info(f"📤 Submitting incident to API Gateway...")
        logger.info(f"Route: {route}, Location: {src_location}")
        success = submit_incident_to_api(incident_data)
        
        if success:
            logger.info("✅ Incident stored successfully via API Gateway")
        else:
            logger.warning("⚠ Failed to store incident via API Gateway")
        
    except Exception as e:
        logger.error(f"Error handling message: {e}", exc_info=True)

while True:
    conn, addr = sock.accept()
    conn.settimeout(5)
    try:
        data = conn.recv(8192)
        if data:
            msg = json.loads(data.decode())
            handle_message(sock, msg, addr)
    except socket.timeout:
        logger.warning("Connection timed out")
    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        conn.close()