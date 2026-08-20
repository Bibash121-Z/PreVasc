import os
from django.apps import AppConfig

class DashboardConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'dashboard'

    def ready(self):
        # ONLY start the MQTT worker inside the main running process (prevents duplicate threads)
        if os.environ.get('RUN_MAIN') == 'true':
            try:
                from .mqtt_worker import client, MQTT_SERVER, MQTT_PORT
                print("🔌 Spawning single background MQTT thread...")
                client.connect(MQTT_SERVER, MQTT_PORT, 60)
                client.loop_start()
            except Exception as e:
                print(f"🔴 MQTT Background thread failed to start: {e}")