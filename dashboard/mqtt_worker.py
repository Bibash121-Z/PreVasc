import os
import collections
import json
import paho.mqtt.client as mqtt
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from paho.mqtt.enums import CallbackAPIVersion
from .peak import PPGProcessor  # Import the processor framework

# --- Block 1: Local Hotspot MQTT Configuration ---
BROKER = "192.168.43.252"  # Adjusted to localhost (or use your active laptop IP)
PORT = 1883
TOPIC = "sensor/vascular"
CONTROL_TOPIC = "sensor/control"  # Dedicated topic for START/STOP actions

MQTT_SERVER = BROKER
MQTT_PORT = PORT
MQTT_TOPIC = TOPIC

# Instantiate processing buffers (5 seconds at 100Hz frequency window = 500 element capacity)
DATA_BUFFER = collections.deque(maxlen=500)
TIME_BUFFER = collections.deque(maxlen=500) # [NEW] Added parallel buffer for ESP32 timestamps
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
        # Also subscribe to the control topic if the backend needs to listen to its own commands
        client.subscribe(CONTROL_TOPIC)
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

        # If the message is arriving on the control topic, ignore processing it as sensor data
        if msg.topic == CONTROL_TOPIC:
            return

        if payload_text == "1":
            return
            
        elif payload_text == "2":
            print("👋 Verified handshake confirmation ('2') received from ESP32!")
            async_to_sync(channel_layer.group_send)(
                "sensor_data", 
                {"type": "broadcast_handshake_success"}
            )
            
        elif payload_text.startswith("["):
            try:
                # Parse the JSON packet from ESP32
                data_batch = json.loads(payload_text)
                
                for item in data_batch:
                    raw_ir = float(item["i"])
                    timestamp_us = float(item["t"]) # Extract exact hardware microsecond timestamp
                    
                    DATA_BUFFER.append(raw_ir)
                    TIME_BUFFER.append(timestamp_us)
                
                # Run complete analytical pipeline once structural minimum elements are met
                if len(DATA_BUFFER) >= 200:
                    results = processor.preprocess_signal(list(DATA_BUFFER))
                    
                    peaks = results["systolic_peaks"]
                    bpm = float(results.get("bpm", 0))

                    # [NEW] Debug check to ensure peak indices align exactly with TIME_BUFFER indices
                    display_len = len(results["display"])
                    buffer_len = len(DATA_BUFFER)
                    if display_len != buffer_len:
                        print(f"⚠️ WARNING: Array length mismatch! Display length ({display_len}) != Buffer length ({buffer_len}). Peak indices may not align correctly with TIME_BUFFER.")

                    # [NEW] Recalculate true BPM using exact time gaps between hardware peaks
                    if len(peaks) >= 2:
                        import statistics
                        # Extract the exact microsecond timestamp for each mapped peak index
                        peak_times = [TIME_BUFFER[idx] for idx in peaks if idx < len(TIME_BUFFER)]
                        
                        if len(peak_times) >= 2:
                            # Calculate time diff (RR intervals) between consecutive beats in microseconds
                            rr_intervals = [peak_times[i] - peak_times[i-1] for i in range(1, len(peak_times))]
                            
                            # First pass: Medical absolute bounds filter (40-220 BPM)
                            valid_rr = [rr for rr in rr_intervals if 272000 <= rr <= 1500000]
                            
                            if valid_rr:
                                # First pass median
                                initial_median = statistics.median(valid_rr)
                                
                                # Second pass: Relative consistency filter (discard false gaps / missed beats > 1.5x the median gap)
                                clean_rr = [rr for rr in valid_rr if rr <= (1.5 * initial_median)]
                                
                                if len(clean_rr) >= 2:
                                    # Calculate final reliable medical BPM
                                    final_median_rr_us = statistics.median(clean_rr)
                                    bpm = 60000000.0 / final_median_rr_us 
                                else:
                                    # If fewer than 2 clean intervals remain, our data is too noisy; fallback to default processor BPM
                                    print("⚠️ Not enough clean RR intervals, falling back to basic processing BPM.")
                                    # bpm remains the fallback `float(results.get("bpm", 0))` we assigned at the top

                    # Package and transmit calculated data sets to the active consumer group
                    async_to_sync(channel_layer.group_send)(
                        "sensor_data",
                        {
                            "type": "send_sensor_data", 
                            "display": results["display"].tolist() if hasattr(results["display"], 'tolist') else list(results["display"]),
                            "systolic_peaks": peaks.tolist() if hasattr(peaks, 'tolist') else list(peaks),
                            "bpm": round(bpm, 1) # Display to 1 decimal point for clinical accuracy
                        }
                    )
            except (json.JSONDecodeError, ValueError, KeyError) as e:
                print(f"⚠️ Data parsing error: {e}")
            
    except Exception as e:
        print(f"🔴 Background message processing failure: {e}")

# --- Block 5: Outbound Command Handlers ---

def send_ping_to_esp():
    """
    Sends the initial handshake ping ('1') to the ESP32 using the primary data topic.
    """
    print(f"📤 Publishing local handshake request '1' to topic '{TOPIC}'...")
    client.publish(TOPIC, "1", retain=False)

def send_command_to_esp(command_string):
    """
    Publishes device commands (like 'START_MEASURE' or 'STOP_MEASURE') to the ESP32.
    Reuses the client instance, broker settings, and utilizes the control channel.
    """
    try:
        print(f"📡 Publishing control command '{command_string}' to topic '{CONTROL_TOPIC}'...")
        # Use the already initialized global client instance to publish
        client.publish(CONTROL_TOPIC, command_string, retain=False)
    except Exception as e:
        print(f"❌ Failed to publish MQTT command '{command_string}': {e}")


# --- Block 6: MQTT Client Instantiation & Hooks ---
client = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2, transport="tcp")
mqtt_client = client

client.on_connect = on_connect 
client.on_message = on_message