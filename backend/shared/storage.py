import os

from django.apps import apps
from django.conf import settings
from django.core.files.storage import FileSystemStorage, storages
from django.db import models
from django.db.models import ProtectedError

from shared.db import on_commit

PRIVATE_STORAGE_ALIAS = "private"

SWEPT_STORAGE_PREFIXES = ("companies", "documents")

RETAINED_STORAGE_PREFIXES = ("users",)

RETAINED_AFTER_ROW_DELETE = {
    "documents.Document": (
        "Supporting payslips inherit their classification retention clock and use a retained storage prefix. "
        "Only unattached documents use ordinary deletion and orphan cleanup; the document retention task "
        "purges linked files and every extraction after the claim horizon."
    ),
    "users.InvestorClassification": (
        "Classification evidence has a statutory retention horizon and outlives its row deliberately. "
        "purge_classification_evidence is the only thing that removes it, and a row carrying evidence "
        "should not be hard-deleted at all: see issue #177."
    ),
}

CONDITIONALLY_RETAINED = {"documents.Document": "classification_id"}


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
            if (
                field.deconstruct()[3].get("storage") is private_storage
                or field.storage is private_storage()
                or isinstance(field.storage, PrivateMediaStorage)
            ):
                yield model, field.name


def swept_file_fields():
    for model, field_name in private_file_fields():
        if model._meta.label not in RETAINED_AFTER_ROW_DELETE or model._meta.label in CONDITIONALLY_RETAINED:
            yield model, field_name


def _delete_stored_file(storage, name):
    def delete():
        storage.delete(name)

    on_commit(delete)


def protect_retained_file(sender, instance, **kwargs):
    condition = CONDITIONALLY_RETAINED.get(sender._meta.label)
    if condition and getattr(instance, condition) and instance.file:
        raise ProtectedError("Supporting evidence must reach its retention horizon before purging.", [instance])


def delete_file_when_the_row_is_gone(field_name):
    def receiver(sender, instance, **kwargs):
        retained_when = CONDITIONALLY_RETAINED.get(sender._meta.label)
        if retained_when and getattr(instance, retained_when):
            return
        stored = getattr(instance, field_name, None)
        if stored and stored.name:
            _delete_stored_file(stored.storage, stored.name)

    return receiver
