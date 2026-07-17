import json
from channels.generic.websocket import WebsocketConsumer
from asgiref.sync import async_to_sync

class SensorConsumer(WebsocketConsumer):
    
    # --- Block 1: Web browser connect handler ---
    # This block accepts the user's browser connection and joins them to the shared live data channel
    def connect(self):
        self.group_name = "sensor_data"
        async_to_sync(self.channel_layer.group_add)(self.group_name, self.channel_name)
        self.accept()
        
        # Track that this specific socket is active
        self.is_connected = True
        print(f"🟢 WebSocket open and accepted: {self.channel_name}")

    # --- Block 2: Web browser disconnect handler ---
    # This block cleans up references when the user closes their browser tab
    def disconnect(self, close_code):
        # Mark as disconnected immediately to block incoming writes
        self.is_connected = False
        async_to_sync(self.channel_layer.group_discard)(self.group_name, self.channel_name)
        print(f"🔴 WebSocket closed: {self.channel_name}")

    # --- Block 3: Browser actions receiver ---
    # This block reads custom button clicks from your browser page and triggers the MQTT ping helper
    def receive(self, text_data):
        try:
            data = json.loads(text_data)
            action = data.get('action')
            
            if action == 'connect_device':
                print("⚡ Web click detected! Triggering outbound MQTT Handshake request...")
                from .mqtt_worker import send_ping_to_esp
                send_ping_to_esp()
                
        except Exception as e:
            print(f"🔴 Error in consumer receive: {e}")

    # --- Block 4: Sensor stream relay handler (UPDATED FOR WEB UI + DISCONNECT PROTECTION) ---
    def send_sensor_data(self, event):
        # Only attempt to transmit if the socket is actively open
        if getattr(self, "is_connected", False):
            try:
                self.send(text_data=json.dumps({
                    "type": "sensor_stream",
                    "display": event.get("display", []),
                    "systolic_peaks": event.get("systolic_peaks", []),
                    "bpm": event.get("bpm", 0.0)
                }))
            except Exception:
                # Catch any remaining abrupt closures gracefully
                self.is_connected = False
        
    # --- Block 5: Handshake verification relay ---
    # This block notifies the front-end interface that the ESP32 successfully responded to the handshake ping
    def broadcast_handshake_success(self, event):
        # Only attempt to transmit if the socket is actively open
        if getattr(self, "is_connected", False):
            try:
                print("📥 Relaying handshake success frame to browser front-end UI...")
                self.send(text_data=json.dumps({
                    "type": "broadcast_handshake_success"
                }))
            except Exception:
                self.is_connected = False

        # --- Block 3: Browser actions receiver ---
    # This block reads custom button clicks from your browser page and triggers the MQTT handlers
    def receive(self, text_data):
        try:
            data = json.loads(text_data)
            action = data.get('action')
            
            # --- START CAPTURE ACTION ---
            if action == 'start_capture':
                print("⚡ UI requested Start Capture! Publishing START_MEASURE to ESP32...")
                from .mqtt_worker import send_command_to_esp
                send_command_to_esp("START_MEASURE")
                
            # --- STOP CAPTURE ACTION ---
            elif action == 'stop_capture':
                print("🛑 UI requested Stop Capture! Publishing STOP_MEASURE to ESP32...")
                from .mqtt_worker import send_command_to_esp
                send_command_to_esp("STOP_MEASURE")
                
            # Keep your old handshake verification logic here if you still use it
            elif action == 'connect_device':
                print("⚡ Web click detected! Triggering outbound MQTT Handshake request...")
                from .mqtt_worker import send_ping_to_esp
                send_ping_to_esp()
                
        except Exception as e:
            print(f"🔴 Error in consumer receive: {e}")