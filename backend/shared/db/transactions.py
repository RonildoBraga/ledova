from functools import wraps

from django.db import transaction

from .aliases import current_alias


class _Atomic:

    def __init__(self, using=None, savepoint=True, durable=False):
        self.using = using
        self.savepoint = savepoint
        self.durable = durable
        self._inner = None

    def _bound(self):
        return transaction.atomic(self.using or current_alias(), self.savepoint, self.durable)

    def __enter__(self):
        self._inner = self._bound()
        return self._inner.__enter__()

    def __exit__(self, exc_type, exc_value, traceback):
        inner, self._inner = self._inner, None
        return inner.__exit__(exc_type, exc_value, traceback)

    def __call__(self, func):
        @wraps(func)
        def inner(*args, **kwargs):
            with _Atomic(self.using, self.savepoint, self.durable):
                return func(*args, **kwargs)

        return inner


def atomic(using=None, savepoint=True, durable=False):
    if callable(using):
        return _Atomic(None, savepoint, durable)(using)
    return _Atomic(using, savepoint, durable)


def on_commit(func, using=None, robust=False):
    return transaction.on_commit(func, using=using or current_alias(), robust=robust)
