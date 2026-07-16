import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

# --- Block 1: Initializing Django configurations ---
# This block sets up environment flags and starts the standard web handler safely
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'vascular_dashboard.settings')
django_asgi_app = get_asgi_application()

import dashboard.routing

# --- Block 2: Handing off web traffic vs live data traffic ---
# This block separates standard website page loads from live real-time browser connections
application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(
            dashboard.routing.websocket_urlpatterns
        )
    ),
})