import json
import subprocess
import sys

from django.conf import settings
from django.test import SimpleTestCase

from ledova_backend.procrastinate_app import app
from shared.tasks.catalogue import CLASSIFIED, PRINCIPAL_BEARING, SYSTEM_WIDE

WHAT_A_WORKER_IMPORTS = """
import django, json, os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ledova_backend.settings.test")
django.setup()
from ledova_backend.procrastinate_app import app
print(json.dumps(sorted(app.tasks)))
"""


def tasks_a_worker_would_find():
    finished = subprocess.run(
        [sys.executable, "-c", WHAT_A_WORKER_IMPORTS],
        capture_output=True,
        text=True,
        cwd=settings.BASE_DIR,
        check=True,
    )
    return set(json.loads(finished.stdout.strip().splitlines()[-1]))


class EveryTaskSaysWhoItActsForTest(SimpleTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.registered = tasks_a_worker_would_find()

    def test_every_task_a_worker_would_find_is_classified(self):
        self.assertEqual(sorted(self.registered - set(CLASSIFIED)), [])

    def test_no_classification_names_a_task_the_worker_would_not_find(self):
        self.assertEqual(sorted(set(CLASSIFIED) - self.registered), [])

    def test_a_task_is_system_wide_or_principal_bearing_and_not_both(self):
        self.assertEqual(sorted(set(SYSTEM_WIDE) & set(PRINCIPAL_BEARING)), [])

    def test_every_entry_states_a_reason_rather_than_a_label(self):
        for name, reason in CLASSIFIED.items():
            with self.subTest(task=name):
                self.assertGreater(len(reason), 30, f"{name} needs a reason, not a label")

    def test_an_unclassified_task_would_be_reported_rather_than_ignored(self):
        classified = set(CLASSIFIED) - {"wallets.tasks.sync.sync_wallet"}

        self.assertEqual(sorted(self.registered - classified), ["wallets.tasks.sync.sync_wallet"])

    def test_the_worker_registry_is_smaller_than_this_process_can_reach(self):
        self.assertGreater(len(self.registered), 20)
        self.assertLessEqual(self.registered, set(app.tasks))
