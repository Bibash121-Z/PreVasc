import json
from channels.generic.websocket import WebsocketConsumer
from asgiref.sync import async_to_sync

class SensorConsumer(WebsocketConsumer):
    
    # --- Block 1: Web browser connect handler ---
    def connect(self):
        self.group_name = "sensor_data"
        async_to_sync(self.channel_layer.group_add)(self.group_name, self.channel_name)
        self.accept()
        
        # Track that this specific socket is active
        self.is_connected = True
        print(f"🟢 WebSocket open and accepted: {self.channel_name}")

    # --- Block 2: Web browser disconnect handler ---
    def disconnect(self, close_code):
        # Mark as disconnected immediately to block incoming writes
        self.is_connected = False
        async_to_sync(self.channel_layer.group_discard)(self.group_name, self.channel_name)
        print(f"🔴 WebSocket closed: {self.channel_name}")

    # --- Block 3: Browser actions receiver ---
    def receive(self, text_data):
        try:
            data = json.loads(text_data)
            action = data.get('action')
            from .mqtt_worker import send_command_to_esp, send_ping_to_esp, set_session_state, stop_session
            
            if action == 'start_capture':
                age = float(data.get('age', 30.0))
                height_m = float(data.get('height_m', 1.75))
                enable_ppg = bool(data.get('enable_ppg', True))
                enable_pcg = bool(data.get('enable_pcg', True))
                
                print(f"📥 [WEBSOCKET] Received Session Config -> Age: {age} yrs, Height: {height_m} m")
                
                # Update backend worker memory directly
                set_session_state(age, height_m, enable_ppg, enable_pcg)
                send_command_to_esp("START_MEASURE")
                
            elif action == 'stop_capture':
                print("🛑 UI requested Stop Capture! Publishing STOP_MEASURE to ESP32...")
                stop_session()
                send_command_to_esp("STOP_MEASURE")
                
            elif action == 'connect_device':
                print("⚡ Web click detected! Triggering outbound MQTT Handshake request...")
                send_ping_to_esp()
                
        except Exception as e:
            print(f"🔴 Error in consumer receive: {e}")
            
            
    # --- Block 4: Sensor stream relay handler ---
    def send_sensor_data(self, event):
        if getattr(self, "is_connected", False):
            try:
                self.send(text_data=json.dumps({
                    "type": "sensor_stream",
                    "display": event.get("display", []),
                    "systolic_peaks": event.get("systolic_peaks", []),
                    "pcg": event.get("pcg", []),
                    "s1_peaks": event.get("s1_peaks", []),
                    "s2_peaks": event.get("s2_peaks", []),
                    "bpm": event.get("bpm", 0.0),
                    "ai_metrics": event.get("ai_metrics", {}),
                    "clinical_status": event.get("clinical_status", "CALIBRATING...")
                }))
            except Exception:
                self.is_connected = False
                  
    # --- Block 5: Handshake verification relay ---
    def broadcast_handshake_success(self, event):
        if getattr(self, "is_connected", False):
            try:
                print("📥 Relaying handshake success frame to browser front-end UI...")
                self.send(text_data=json.dumps({
                    "type": "broadcast_handshake_success"
                }))
            except Exception:
                self.is_connected = False