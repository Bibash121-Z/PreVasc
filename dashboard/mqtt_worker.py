import os
import collections
import paho.mqtt.client as mqtt
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from paho.mqtt.enums import CallbackAPIVersion
from .peak import PPGProcessor  # Import the processor framework

# --- Block 1: Local Hotspot MQTT Configuration ---
BROKER = "192.168.43.252" 
PORT = 1883
TOPIC = "sensor/vascular"

MQTT_SERVER = BROKER
MQTT_PORT = PORT
MQTT_TOPIC = TOPIC

# Instantiate processing buffers (5 seconds at 100Hz frequency window = 500 element capacity)
DATA_BUFFER = collections.deque(maxlen=500)
processor = PPGProcessor(fs=100)

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

# --- Block 4: Handshake & Data Receiver (CONNECTED TO SCIPY PROCESSING CORE) ---
def on_message(client, userdata, msg):
    try:
        payload = msg.payload
        channel_layer = get_channel_layer()

        try:
            payload_text = payload.decode('utf-8').strip()
        except UnicodeDecodeError:
            return

        if payload_text == "1":
            return
            
        elif payload_text == "2":
            print("👋 Verified handshake confirmation ('2') received from ESP32!")
            async_to_sync(channel_layer.group_send)(
                "sensor_data", 
                {"type": "broadcast_handshake_success"}
            )
            
        elif "," in payload_text:
            try:
                red_val, ir_val = payload_text.split(",")
                raw_ir = float(ir_val.strip())
                
                # Append raw input coordinate directly into sliding window calculation array
                DATA_BUFFER.append(raw_ir)
                
                # Run complete analytical pipeline once structural minimum elements are met
                if len(DATA_BUFFER) >= 200:
                    results = processor.preprocess_signal(list(DATA_BUFFER))
                    
                    # Package and transmit calculated data sets to the active consumer group
                    async_to_sync(channel_layer.group_send)(
                        "sensor_data",
                        {
                            "type": "send_sensor_data", # Maps to send_sensor_data() in consumer
                            "display": results["display"].tolist(),
                            "systolic_peaks": results["systolic_peaks"].tolist(),
                            "bpm": float(results["bpm"])
                        }
                    )
            except ValueError:
                print(f"⚠️ Received poorly formatted data: {payload_text}")
            
    except Exception as e:
        print(f"🔴 Background message processing failure: {e}")

def send_ping_to_esp():
    print(f"📤 Publishing local handshake request '1' to topic '{TOPIC}'...")
    client.publish(TOPIC, "1", retain=False)

client = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2, transport="tcp")
mqtt_client = client

client.on_connect = on_connect
client.on_message = on_message