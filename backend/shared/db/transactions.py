from django.db import transaction

from .aliases import current_alias


def atomic(using=None, savepoint=True, durable=False):
    return transaction.atomic(using=using or current_alias(), savepoint=savepoint, durable=durable)


def on_commit(func, using=None, robust=False):
    return transaction.on_commit(func, using=using or current_alias(), robust=robust)
