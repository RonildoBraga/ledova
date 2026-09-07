from datetime import timedelta

from django.utils import timezone

from shared.storage import (
    SWEPT_STORAGE_PREFIXES,
    private_storage,
    swept_file_fields,
)

GRACE = timedelta(hours=24)


def referenced_names():
    names = set()
    for model, field_name in swept_file_fields():
        rows = (
            model.objects.exclude(**{field_name: ""})
            .exclude(**{f"{field_name}__isnull": True})
            .values_list(field_name, flat=True)
        )
        names.update(rows.iterator())
    return names


def _walk(storage, prefix):
    try:
        directories, files = storage.listdir(prefix)
    except (FileNotFoundError, NotADirectoryError):
        return

    for name in files:
        yield f"{prefix}/{name}" if prefix else name

    for directory in directories:
        yield from _walk(storage, f"{prefix}/{directory}" if prefix else directory)


def _settled_before(storage, name, cutoff):
    try:
        return storage.get_modified_time(name) < cutoff
    except (FileNotFoundError, NotImplementedError, OSError):
        return False


def orphaned_files(moment=None, storage=None):
    storage = storage or private_storage()
    cutoff = (moment or timezone.now()) - GRACE
    referenced = referenced_names()

    found = [
        name
        for prefix in SWEPT_STORAGE_PREFIXES
        for name in _walk(storage, prefix)
        if name not in referenced and _settled_before(storage, name, cutoff)
    ]
    return sorted(found)


def sweep_orphaned_files(moment=None, storage=None, dry_run=False):
    storage = storage or private_storage()
    names = orphaned_files(moment=moment, storage=storage)
    if dry_run:
        return {"found": len(names), "deleted": 0, "failed": 0, "names": names}

    deleted = failed = 0
    for name in names:
        try:
            storage.delete(name)
        except Exception:
            failed += 1
            continue
        deleted += 1

    return {"found": len(names), "deleted": deleted, "failed": failed, "names": names}
