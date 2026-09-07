import json
import subprocess
import sys

from django.conf import settings
from django.test import SimpleTestCase

from ledova_backend.procrastinate_app import app
from shared.tasks.catalogue import (
    CLASSIFIED,
    PRINCIPAL_BEARING,
    READS_MUST_SURVIVE_THE_POLICIES,
    SYSTEM_WIDE,
)

WHAT_IS_DECLARED = """
import django, json, os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ledova_backend.settings.test")
django.setup()
from ledova_backend.procrastinate_app import app
print(json.dumps(sorted(app.tasks)))
"""


def declared_tasks():
    finished = subprocess.run(
        [sys.executable, "-c", WHAT_IS_DECLARED],
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
        cls.declared = declared_tasks()

    def test_every_declared_task_is_classified(self):
        self.assertEqual(sorted(self.declared - set(CLASSIFIED)), [])

    def test_no_classification_names_a_task_nothing_declares(self):
        self.assertEqual(sorted(set(CLASSIFIED) - self.declared), [])

    def test_a_task_is_system_wide_or_principal_bearing_and_not_both(self):
        self.assertEqual(sorted(set(SYSTEM_WIDE) & set(PRINCIPAL_BEARING)), [])

    def test_every_entry_states_a_reason_rather_than_a_label(self):
        for name, reason in CLASSIFIED.items():
            with self.subTest(task=name):
                self.assertGreater(len(reason), 30, f"{name} needs a reason, not a label")

    def test_an_unclassified_task_would_be_reported_rather_than_ignored(self):
        classified = set(CLASSIFIED) - {"wallets.tasks.sync.sync_wallet"}

        self.assertEqual(sorted(self.declared - classified), ["wallets.tasks.sync.sync_wallet"])

    def test_the_subprocess_answered_with_a_registry_rather_than_with_nothing(self):
        self.assertGreater(len(self.declared), 20)
        self.assertLessEqual(self.declared, set(app.tasks))


class AConversionMustProveItsReadsSurviveTheSelectPoliciesTest(SimpleTestCase):

    def test_every_noted_trap_names_a_task_that_is_principal_bearing(self):
        self.assertEqual(sorted(set(READS_MUST_SURVIVE_THE_POLICIES) - set(PRINCIPAL_BEARING)), [])

    def test_every_noted_trap_states_what_would_go_quiet(self):
        for name, reason in READS_MUST_SURVIVE_THE_POLICIES.items():
            with self.subTest(task=name):
                self.assertGreater(len(reason), 120, f"{name} needs the failure named, not the risk labelled")
