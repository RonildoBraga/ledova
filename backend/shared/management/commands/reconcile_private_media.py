import filecmp
import os
import shutil

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from shared.storage import private_file_fields


def stored_names(model, field_name):
    return (
        model.objects.exclude(**{field_name: ""})
        .exclude(**{f"{field_name}__isnull": True})
        .values_list(field_name, flat=True)
        .iterator()
    )


class Command(BaseCommand):
    help = "Move uploads that are sitting under MEDIA_ROOT back under PRIVATE_MEDIA_ROOT."

    def add_arguments(self, parser):
        parser.add_argument("--check", action="store_true")

    def handle(self, *args, **options):
        verbose = options["verbosity"] >= 1
        if getattr(settings, "STORAGE_BACKEND", "") != "local":
            if verbose:
                self.stdout.write("STORAGE_BACKEND is not local: nothing to reconcile.")
            return

        strays = []
        conflicts = []
        for model, field_name in private_file_fields():
            label = f"{model._meta.label}.{field_name}"
            for name in stored_names(model, field_name):
                public = os.path.join(settings.MEDIA_ROOT, name)
                if not os.path.isfile(public):
                    continue
                private = os.path.join(settings.PRIVATE_MEDIA_ROOT, name)
                if os.path.isfile(private) and not filecmp.cmp(public, private, shallow=False):
                    conflicts.append((label, name, public, private))
                else:
                    strays.append((label, name, public, private))

        if verbose:
            for label, name, public, _ in strays:
                self.stdout.write(f"stray {label} {name} at {public}")
        for label, name, public, private in conflicts:
            self.stderr.write(f"conflict {label} {name}: {public} differs from {private}")

        if options["check"]:
            if strays or conflicts:
                raise CommandError(f"{len(strays)} stray and {len(conflicts)} conflicting uploads under MEDIA_ROOT.")
            if verbose:
                self.stdout.write("No uploads found under MEDIA_ROOT.")
            return

        for _, _, public, private in strays:
            if os.path.isfile(private):
                os.remove(public)
                continue
            os.makedirs(os.path.dirname(private), exist_ok=True)
            shutil.move(public, private)

        if verbose:
            self.stdout.write(f"Reconciled {len(strays)} uploads.")
        if conflicts:
            raise CommandError(
                f"{len(conflicts)} uploads exist in both roots with different bytes and were left alone."
            )
