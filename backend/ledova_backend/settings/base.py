import os
from pathlib import Path

from ledova_backend.environment import read_bool

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.environ["SECRET_KEY"]
DEBUG = read_bool("DEBUG", default=False)
ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_extensions",
    "procrastinate.contrib.django",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "storages",
    "authentication",
    "users",  # depends on authentication (includes UserAccount model)
    "portfolios",  # depends on users
    "integrations",
    "assets",
    "wallets",  # depends on users (crypto-native finance)
    "compliance",  # configurable example risk workflows
    "blockchain",  # blockchain transaction tracking
    "companies",  # company registration and listing
    "tokens",  # share tokens, P2P trading, stablecoins
    "whitelist",  # on-chain allowlist example
    "feature_flags",
    "documents",  # uploaded financial docs + LLM extraction
    "shared",
]

MIDDLEWARE = [
    "shared.middleware.HealthCheckMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "feature_flags.middleware.TradingFeatureFlagMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "ledova_backend.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "shared" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "ledova_backend.wsgi.application"
ASGI_APPLICATION = "ledova_backend.asgi.application"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True

# Redis is used only for the trading-events pub/sub channel
# (backend/tokens/events.py). Background tasks run on procrastinate (Postgres).
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
