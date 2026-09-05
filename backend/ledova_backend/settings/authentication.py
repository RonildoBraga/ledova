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


SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(seconds=int(os.environ.get("ACCESS_TOKEN_LIFETIME", 604800))),
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


AUTH_COOKIE = {
    "access": os.environ.get("COOKIE_ACCESS_NAME", "access"),
    "refresh": os.environ.get("COOKIE_REFRESH_NAME", "refresh"),
    "domain": os.environ.get("COOKIE_DOMAIN") or None,
    "secure": read_bool("COOKIE_SECURE", default=not DEBUG),
    "samesite": "Lax",
}


CSRF_COOKIE_DOMAIN = AUTH_COOKIE["domain"]
CSRF_COOKIE_SECURE = AUTH_COOKIE["secure"]
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False
