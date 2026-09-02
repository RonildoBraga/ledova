"""
Authentication and authorization settings for ledova_backend project.
"""

import os
from datetime import timedelta

from ledova_backend.environment import read_canonical_cidr_list

from .base import SECRET_KEY

AUTH_USER_MODEL = "authentication.CustomUser"
V2_TRUSTED_PROXY_CIDRS = read_canonical_cidr_list("V2_TRUSTED_PROXY_CIDRS")

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
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": False,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "VERIFYING_KEY": None,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_TOKEN_CLASSES": ("rest_framework_simplejwt.tokens.AccessToken",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "TOKEN_TYPE_CLAIM": "token_type",
    "JTI_CLAIM": "jti",
    "SLIDING_TOKEN_REFRESH_EXP_CLAIM": "refresh_exp",
    "SLIDING_TOKEN_LIFETIME": timedelta(seconds=1800),
    "SLIDING_TOKEN_REFRESH_LIFETIME": timedelta(seconds=604800),
}
