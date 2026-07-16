from django.urls import re_path
from . import consumers

# --- Block 1: WebSocket route endpoints ---
# This block directs your web browser's live connection string directly to the consumer code
websocket_urlpatterns = [
    re_path(r'^ws/sensor_data/$', consumers.SensorConsumer.as_asgi()),
]