import os
import paho.mqtt.client as mqtt
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from paho.mqtt.enums import CallbackAPIVersion

# --- Block 1: Local Hotspot MQTT Configuration ---
# 'localhost' works if Django and Mosquitto are running on the same PC.
BROKER = "192.168.43.252" 
PORT = 1883
TOPIC = "sensor/vascular"

MQTT_SERVER = BROKER
MQTT_PORT = PORT
MQTT_TOPIC = TOPIC

# --- Block 2: Log Controller ---
LOCK_FILE = os.path.join(os.path.dirname(__file__), ".mqtt_printed.lock")
if os.path.exists(LOCK_FILE) and os.environ.get('RUN_MAIN') != 'true':
    try: os.remove(LOCK_FILE)
    except OSError: pass

# --- Block 3: Successful Connection Action ---
def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        if not os.path.exists(LOCK_FILE):
            try:
                with open(LOCK_FILE, "w") as f: f.write("printed")
                print(f"🟢 Django Background Worker connected to Local Mosquitto Broker ({BROKER}:{PORT})!")
            except OSError: pass
        print(f"📡 Subscribing to local topic: '{TOPIC}'...")
        client.subscribe(TOPIC)
    else:
        print(f"🔴 MQTT Connection failed with status code: {reason_code}")

# --- Block 4: Handshake & Data Receiver ---
def on_message(client, userdata, msg):
    try:
        payload = msg.payload
        channel_layer = get_channel_layer()

        # We decode the incoming text payload safely
        try:
            payload_text = payload.decode('utf-8').strip()
        except UnicodeDecodeError:
            return # Ignore binary/raw data for now

        # 1. Handshake Logic:
        # If we receive '1', it is our own sent ping (or ESP32 receiving it). Ignore it.
        if payload_text == "1":
            return
            
        # If we receive '2', the ESP32 has responded to our ping! Send success to Frontend UI.
        elif payload_text == "2":
            print("👋 Verified handshake confirmation ('2') received from ESP32!")
            async_to_sync(channel_layer.group_send)(
                "sensor_data", 
                {"type": "broadcast_handshake_success"}
            )
            
        # 2. Sensor Data Logic:
        # If the payload contains a comma, it is the raw PPG data from the ESP32: "red_val,ir_val"
        elif "," in payload_text:
            try:
                red_val, ir_val = payload_text.split(",")
                print(f"📥 Received Sensor Data -> RED: {red_val.strip()} | IR: {ir_val.strip()}")
                
                # Optional: Once you are ready to stream to WebSockets, uncomment this block!
                # async_to_sync(channel_layer.group_send)(
                #     "sensor_data", 
                #     {
                #         "type": "broadcast_sensor_data",
                #         "red": int(red_val.strip()),
                #         "ir": int(ir_val.strip())
                #     }
                # )
            except ValueError:
                # Catch instances where network package drops mid-transmit and payload is corrupted
                print(f"⚠️ Received poorly formatted data: {payload_text}")
            
    except Exception as e:
        print(f"🔴 Background message processing failure: {e}")

# --- Block 5: Handshake Publisher (Triggered by Connect Button in Browser) ---
def send_ping_to_esp():
    print(f"📤 Publishing local handshake request '1' to topic '{TOPIC}'...")
    client.publish(TOPIC, "1", retain=False)

# --- Block 6: Creating the background runner client ---
client = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2, transport="tcp")
mqtt_client = client

# Clean local connection: No SSL/TLS, no username, no passwords
client.on_connect = on_connect
client.on_message = on_message