import json
import subprocess
import sys

from django.conf import settings
from django.test import SimpleTestCase

TASK = "documents.tasks.extract.extract_document"

DECLARED = """
import django, json, os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ledova_backend.settings.test")
django.setup()
from ledova_backend.procrastinate_app import app
print(json.dumps(sorted(app.tasks)))
"""

AFTER_THE_URLCONF = """
import django, json, os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ledova_backend.settings.test")
django.setup()
from django.urls import get_resolver
get_resolver().url_patterns
from ledova_backend.procrastinate_app import app
print(json.dumps(sorted(app.tasks)))
"""


def registry(script):
    finished = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=settings.BASE_DIR,
        check=True,
    )
    return set(json.loads(finished.stdout.strip().splitlines()[-1]))


class RegistrationIsDeclaredRatherThanIncidentalTest(SimpleTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.declared = registry(DECLARED)
        cls.after_urls = registry(AFTER_THE_URLCONF)

    def test_django_setup_alone_registers_the_task_the_document_service_defers(self):
        self.assertIn(TASK, self.declared)

    def test_loading_the_urlconf_adds_no_task_that_was_not_already_declared(self):
        self.assertEqual(sorted(self.after_urls - self.declared), [])

    def test_the_subprocesses_answered_with_a_registry_rather_than_with_nothing(self):
        self.assertGreater(len(self.declared), 20)
        self.assertGreater(len(self.after_urls), 20)

    def test_the_service_defers_the_name_that_was_looked_for(self):
        from documents.tasks.extract import extract_document

        self.assertEqual(extract_document.name, TASK)
