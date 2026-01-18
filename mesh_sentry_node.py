import time
from mesh_relay_node import make_socket, send_new, NODE_ID, NODE_LOCATION
from sensor_collector import read_temperature, read_humidity, read_air_quality, read_light_level
from led_controller import flash_led

# -------------------------------
# Sentry-specific configuration
# -------------------------------
POLL_INTERVAL = 5          # seconds between sensor reads
RISK_THRESHOLD = 0.5      # tune based on your ML model
# RISK_THRESHOLD = 0.22      # TODO: FOR DEBUGGING ONLY

# Your teammate's sensor polling function
def get_sensor_data():
    
    temperature = read_temperature()
    humidity = read_humidity()
    air = read_air_quality() # AQI
    light = read_light_level()
    
    sensor_data = {
        "temperature": temperature,
        "humidity": humidity if humidity is not None else -1,
        "air_quality": air,
        "light": light,
    }
    
    print("Sensor Data:\n", sensor_data)
    
    return sensor_data

# Your ML model wrapper
def predict_risk(sensor_map) -> bool:
    """
    Returns a float between 0 and 1.
    """
    # Placeholder — replace with real ML inference
    # Example: simple heuristic
    if sensor_map["humidity"] < 0:
        risk = sensor_map["temperature"] / 100.0
    else:
        risk = sensor_map["temperature"] / 100.0 * (1 - sensor_map["humidity"] / 100.0)
    print(f"Predicted risk: {risk}")
    return risk >= RISK_THRESHOLD

# -------------------------------
# Sentry main loop
# -------------------------------
def main():
    print(f"[{NODE_ID}] starting sentry node")
    sock = make_socket()

    while True:
        sensor_map = get_sensor_data()
        is_risk = predict_risk(sensor_map)

        print(f"[{NODE_ID}] sensors={sensor_map} is_risk={is_risk:.2f}")

        if is_risk:
            payload = {
                "type": "alert",
                "risk": is_risk,
                "sensor_data": sensor_map,
                "metadata": {},
            }

            print(f"[{NODE_ID}] *** RISK ABOVE THRESHOLD — sending alert ***")
            send_new(sock, payload)
            
            flash_led(2)

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
