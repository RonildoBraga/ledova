import os
from copy import deepcopy

_BASE = {
    "ENGINE": "django.db.backends.postgresql",
    "HOST": os.environ.get("POSTGRES_HOST"),
    "PORT": os.environ.get("POSTGRES_PORT"),
    "NAME": os.environ.get("POSTGRES_DB"),
    "USER": os.environ.get("POSTGRES_USER"),
    "PASSWORD": os.environ.get("POSTGRES_PASSWORD"),
    "CONN_MAX_AGE": 300,
    "OPTIONS": {
        "connect_timeout": 10,
        "keepalives": 1,
        "keepalives_idle": 60,
        "keepalives_interval": 10,
        "keepalives_count": 5,
        "sslmode": os.environ.get("POSTGRES_SSLMODE", "prefer"),
    },
}


def _alias(prefix, default_user, **overrides):
    alias = deepcopy(_BASE)
    alias["USER"] = os.environ.get(f"{prefix}_USER", default_user)
    alias["PASSWORD"] = os.environ.get(f"{prefix}_PASSWORD", _BASE["PASSWORD"])
    alias.update(overrides)
    return alias


DATABASES = {
    "default": deepcopy(_BASE),
    "operator": _alias("RLS_OPERATOR_DB", "ledova_operator"),
    "app": _alias("RLS_APP_DB", "ledova_app", CONN_MAX_AGE=0),
}

RLS_AMBIENT_ALIAS = os.environ.get("RLS_AMBIENT_ALIAS", "app")

DATABASE_ROUTERS = ["shared.db.router.LedovaRouter"]

RLS_ROLES = {
    "app": DATABASES["app"]["USER"],
    "operator": DATABASES["operator"]["USER"],
    "migrate": DATABASES["default"]["USER"],
}

RLS_ROLE_PER_REQUEST = False
