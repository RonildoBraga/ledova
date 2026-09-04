import os
from datetime import timedelta

from ledova_backend.environment import read_bool

from .base import DEBUG, SECRET_KEY

AUTH_USER_MODEL = "authentication.CustomUser"

AUTHENTICATION_BACKENDS = ("django.contrib.auth.backends.ModelBackend",)

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Access tokens live 24 hours because neither client refreshes on 401 yet; drop the default to
# 900 seconds once they do. Refresh tokens live 7 days and rotate on every use.
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(seconds=int(os.environ.get("ACCESS_TOKEN_LIFETIME", 86400))),
    "REFRESH_TOKEN_LIFETIME": timedelta(seconds=int(os.environ.get("REFRESH_TOKEN_LIFETIME", 604800))),
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "VERIFYING_KEY": None,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_TOKEN_CLASSES": ("rest_framework_simplejwt.tokens.AccessToken",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "TOKEN_TYPE_CLAIM": "token_type",
    "JTI_CLAIM": "jti",
}

# The dashboard's session cookies; the mobile app sends the same tokens as a Bearer header.
AUTH_COOKIE = {
    "access": os.environ.get("COOKIE_ACCESS_NAME", "access"),
    "refresh": os.environ.get("COOKIE_REFRESH_NAME", "refresh"),
    "domain": os.environ.get("COOKIE_DOMAIN") or None,
    "secure": read_bool("COOKIE_SECURE", default=not DEBUG),
    "samesite": "Lax",
}
