import os
import sys
from django.apps import AppConfig

class DashboardConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'dashboard'

    def ready(self):
        # 1. Skip running background threads during management tasks (like migrate, makemigrations)
        if 'manage.py' in sys.argv:
            # We only want this thread running if we are actively running the server
            if not any(arg in sys.argv for arg in ['runserver', 'run_worker']):
                return

        # 2. Allow startup if RUN_MAIN is true (WSGI runserver) OR if running under Daphne/ASGI
        # Daphne doesn't use the auto-reloader sub-process, so we can check if RUN_MAIN is True, OR
        # if RUN_MAIN is absent but we are running a Daphne server.
        is_wsgi_main_process = os.environ.get('RUN_MAIN') == 'true'
        is_asgi_daphne = os.environ.get('RUN_MAIN') is None  # Daphne runs single-process

        if is_wsgi_main_process or is_asgi_daphne:
            import threading
            from . import mqtt_worker 
            
            def run_client():
                try:
                    print("🔌 Spawning background MQTT thread...")
                    mqtt_worker.client.connect(mqtt_worker.MQTT_SERVER, mqtt_worker.MQTT_PORT, 60)
                    mqtt_worker.client.loop_forever()
                except Exception as e:
                    print(f"🔴 MQTT Background thread failed to start: {e}")

            mqtt_thread = threading.Thread(target=run_client)
            mqtt_thread.daemon = True
            mqtt_thread.start()