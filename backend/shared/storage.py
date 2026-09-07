import os

from django.apps import apps
from django.conf import settings
from django.core.files.storage import FileSystemStorage, storages
from django.db import models, transaction

PRIVATE_STORAGE_ALIAS = "private"

SWEPT_STORAGE_PREFIXES = ("companies", "documents")

RETAINED_STORAGE_PREFIXES = ("users",)

RETAINED_AFTER_ROW_DELETE = {
    "users.InvestorClassification": (
        "Classification evidence has a statutory retention horizon and outlives its row deliberately. "
        "purge_classification_evidence is the only thing that removes it, and a row carrying evidence "
        "should not be hard-deleted at all: see issue #177."
    ),
}


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


def private_file_fields():
    for model in apps.get_models():
        for field in model._meta.get_fields():
            if not isinstance(field, models.FileField):
                continue
            if isinstance(getattr(field, "storage", None), PrivateMediaStorage):
                yield model, field.name


def swept_file_fields():
    for model, field_name in private_file_fields():
        if model._meta.label not in RETAINED_AFTER_ROW_DELETE:
            yield model, field_name


def _delete_stored_file(storage, name):
    def delete():
        storage.delete(name)

    transaction.on_commit(delete)


def delete_file_when_the_row_is_gone(field_name):
    def receiver(sender, instance, **kwargs):
        stored = getattr(instance, field_name, None)
        if stored and stored.name:
            _delete_stored_file(stored.storage, stored.name)

    return receiver
