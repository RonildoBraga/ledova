import json
import subprocess
import sys

from django.conf import settings
from django.test import SimpleTestCase

TASK = "documents.tasks.extract.extract_document"

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


class TheExtractionTaskIsRegisteredWhereItRunsTest(SimpleTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.registered = tasks_a_worker_would_find()

    def test_a_worker_finds_the_task_the_document_service_defers(self):
        self.assertIn(TASK, self.registered)

    def test_the_registry_read_this_way_is_the_workers_and_not_this_process(self):
        from ledova_backend.procrastinate_app import app

        self.assertGreater(len(self.registered), 20)
        self.assertLessEqual(self.registered, set(app.tasks))

    def test_the_service_defers_the_name_that_was_looked_for(self):
        from documents.tasks.extract import extract_document

        self.assertEqual(extract_document.name, TASK)
