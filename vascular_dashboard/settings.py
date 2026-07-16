"""
Django settings for vascular_dashboard project.
"""

from pathlib import Path

# --- Block 1: Basic project setup ---
# This block defines where your project lives on your computer and sets up its unique security key
BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = 'django-insecure-=o--04$5x0$ywk4a7sfi6xm7m%&8cf(a78!_4*swopxann4g7#'
DEBUG = True

# Allows any device on your mobile hotspot network to access the Django server without host errors
ALLOWED_HOSTS = ["*"]


# --- Block 2: Installed applications list ---
# This block lists all active features and folders Django should load, including Daphne for WebSockets
INSTALLED_APPS = [
    "daphne",
    "channels",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "dashboard.apps.DashboardConfig",
]


# --- Block 3: Security and session middlewares ---
# This block handles safety checks and login sessions whenever someone visits the website
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# --- Block 4: Routing and template configurations ---
# This block points Django to your URLs, HTML files, and activates the live WebSocket network runner
ROOT_URLCONF = "vascular_dashboard.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]
WSGI_APPLICATION = "vascular_dashboard.wsgi.application"
ASGI_APPLICATION = "vascular_dashboard.asgi.application"


# --- Block 5: Database configuration ---
# This block sets up a simple local database file to store any website records
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}


# --- Block 6: Password validation safety rules ---
# This block ensures that user passwords cannot be too weak or simple
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# --- Block 7: Internationalization and timezone settings ---
# This block controls the website's default language and current clock timezone settings
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


# --- Block 8: Static files configuration ---
# This block helps Django find your design stylesheets like CSS and front-end scripts
STATIC_URL = "static/"
STATICFILES_FINDERS = [
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
]


# --- Block 9: Live data layers setup ---
# This block enables the internal messaging system that lets Django and the background MQTT worker chat in real-time
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    },
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"