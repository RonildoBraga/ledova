import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage, storages

PRIVATE_STORAGE_ALIAS = "private"


class PrivateMediaStorage(FileSystemStorage):

    @property
    def base_location(self):
        return settings.PRIVATE_MEDIA_ROOT

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    @property
    def base_url(self):
        return None


def private_storage():
    return storages[PRIVATE_STORAGE_ALIAS]
