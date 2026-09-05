import os

from ledova_backend.environment import resolve_storage_backend

from .base import BASE_DIR, DEBUG

STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")

_STATIC_SOURCE_DIR = os.path.join(BASE_DIR, "static")
STATICFILES_DIRS = [_STATIC_SOURCE_DIR] if os.path.isdir(_STATIC_SOURCE_DIR) else []

STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
]


_STATICFILES_STORAGE = {
    "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
}

_storage_backend = resolve_storage_backend(debug=DEBUG)

if _storage_backend == "local":
    MEDIA_URL = "/media/"
    MEDIA_ROOT = os.path.join(BASE_DIR, "media")
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": _STATICFILES_STORAGE,
    }
else:
    if _storage_backend == "s3":

        STORAGES = {
            "default": {
                "BACKEND": "storages.backends.s3.S3Storage",
                "OPTIONS": {
                    "bucket_name": os.environ["AWS_STORAGE_BUCKET_NAME"],
                    "region_name": os.environ.get("AWS_S3_REGION_NAME", "ap-southeast-2"),
                    "default_acl": None,
                    "querystring_auth": True,
                    "querystring_expire": 300,
                    "file_overwrite": False,
                    "signature_version": "s3v4",
                },
            },
            "staticfiles": _STATICFILES_STORAGE,
        }
    elif _storage_backend == "gcs":

        STORAGES = {
            "default": {
                "BACKEND": "storages.backends.gcloud.GoogleCloudStorage",
                "OPTIONS": {
                    "bucket_name": os.environ["GS_BUCKET_NAME"],
                    "default_acl": None,
                    "querystring_auth": True,
                    "expiration": 300,
                    "file_overwrite": False,
                },
            },
            "staticfiles": _STATICFILES_STORAGE,
        }
