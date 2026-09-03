import os

CORS_ALLOW_CREDENTIALS = True

CORS_ALLOWED_ORIGINS = (
    os.getenv("DJANGO_CORS_ALLOWED_ORIGINS", "").split(",") if os.getenv("DJANGO_CORS_ALLOWED_ORIGINS") else []
)
CSRF_TRUSTED_ORIGINS = (
    os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS") else []
)
