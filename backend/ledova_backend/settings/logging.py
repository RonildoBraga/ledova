"""
Logging settings for ledova_backend project.
"""

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "procrastinate_console": {
            "level": "WARNING",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": True,
        },
        "ledova_backend": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
        "procrastinate": {
            "handlers": ["procrastinate_console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}
