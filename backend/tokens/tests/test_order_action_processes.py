import json
import os
import select
import signal
import subprocess
import sys
import tempfile
import time
from copy import deepcopy
from pathlib import Path
from unittest import skipUnless

from django.conf import settings
from django.db import connection, connections
from rest_framework.test import APITransactionTestCase

from shared.db import use_operator
from shared.tests.scoped import RunsOnTheScopedConnection
from tokens.models import OrderModificationLog, SigningChallenge
from tokens.tests.order_action_fixtures import ActionFixtures


class ActionChild:
    def __init__(self, case, directory, phase, body):
        self.errors = tempfile.TemporaryFile(mode="w+")
        self.process = subprocess.Popen(
            [sys.executable, "-m", "tokens.tests.order_action_worker"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.errors,
            text=True,
            env={**os.environ, "ORDER_ACTION_TEST_DATABASES": json.dumps(case.worker_databases(), default=str)},
        )
        case.addCleanup(self.close)
        self.process.stdin.write(
            json.dumps(
                {
                    "phase": phase,
                    "directory": str(directory),
                    "body": body,
                    "user_id": case.tenant.user.pk,
                    "order_id": str(case.order.pk),
                }
            )
            + "\n"
        )
        self.process.stdin.flush()

    def read(self):
        if not select.select([self.process.stdout], [], [], 20)[0]:
            raise AssertionError("The owned action worker did not reach its expected stage")
        line = self.process.stdout.readline()
        if not line:
            raise AssertionError(f"The owned action worker ended before its result: {self.error_output()}")
        return json.loads(line)

    def error_output(self):
        self.errors.seek(0)
        return self.errors.read()[-5000:]

    def release(self):
        self.process.stdin.write("continue\n")
        self.process.stdin.flush()

    def wait(self):
        return self.process.wait(timeout=20)

    def close(self):
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait(timeout=10)
        self.process.stdin.close()
        self.process.stdout.close()
        self.errors.close()


class ActionProcessChecks(ActionFixtures):
    def worker_databases(self):
        base = deepcopy(connections["default"].settings_dict)
        base["CONN_MAX_AGE"] = 0
        result = {"default": base}
        for alias in ("app", "operator"):
            result[alias] = deepcopy(base)
            result[alias]["USER"] = settings.DATABASES[alias]["USER"]
            result[alias]["PASSWORD"] = settings.DATABASES[alias]["PASSWORD"]
        return result

    def crash(self, phase):
        signed = self.signed("modify", self.modify_body())
        with tempfile.TemporaryDirectory(prefix="order-action-crash-") as temporary:
            directory = Path(temporary)
            child = ActionChild(self, directory, phase, signed)
            self.assertEqual(child.wait(), -signal.SIGKILL, child.error_output())
            recovered = self.recover()
            self.assertEqual(recovered.status_code, 200, recovered.content)
            with use_operator():
                consumed = SigningChallenge.objects.get(digest=signed["digest"]).is_consumed
                self.order.refresh_from_db()
                log_count = OrderModificationLog.objects.filter(order=self.order).count()
            if phase == "committed":
                self.assertEqual(recovered.json()["status"], "applied")
                self.assertTrue(consumed)
                self.assertEqual((self.order.quantity, self.order.modification_count, log_count), (12, 1, 3))
                events = [json.loads(line) for line in (directory / "events.jsonl").read_text().splitlines()]
                self.assertEqual(events, [{"event": "order_modified", "alias": "app"}])
            else:
                self.assertEqual(recovered.json()["status"], "pending")
                self.assertFalse(consumed)
                self.assertEqual((self.order.quantity, self.order.modification_count, log_count), (10, 0, 0))
                self.assertFalse((directory / "events.jsonl").exists())
            retry = self.execute("modify", signed)
            self.assertEqual(retry.status_code, 200, retry.content)
            self.assertEqual(self.recover().json(), retry.json())
            with use_operator():
                self.order.refresh_from_db()
                self.assertEqual(self.order.modification_count, 1)
                self.assertEqual(OrderModificationLog.objects.filter(order=self.order).count(), 3)
                self.assertTrue(SigningChallenge.objects.get(digest=signed["digest"]).is_consumed)
            self.assertEqual(len(self.events), 0 if phase == "committed" else 1)

    def test_process_death_after_spend_leaves_a_pending_action_and_unspent_challenge(self):
        self.crash("spent")

    def test_process_death_after_modification_rolls_back_order_logs_and_spend(self):
        self.crash("applied")

    def test_process_death_after_commit_recovers_the_recorded_result_once(self):
        self.crash("committed")

    def test_independent_app_requests_for_one_action_serialize_and_recover_one_result(self):
        first = self.signed("modify", self.modify_body())
        second = self.signed("modify", self.modify_body())
        with tempfile.TemporaryDirectory(prefix="order-action-retry-") as temporary:
            directory = Path(temporary)
            one = ActionChild(self, directory, "pause", first)
            locked = one.read()
            self.assertEqual(locked["stage"], "locked")
            self.assertEqual(locked["database_user"], settings.RLS_ROLES["app"])
            two = ActionChild(self, directory, "compete", second)
            selecting = two.read()
            self.assertEqual(selecting["stage"], "selecting")
            self.assertEqual(selecting["database_user"], settings.RLS_ROLES["app"])
            self.assertNotEqual(locked["pid"], selecting["pid"])
            deadline = time.monotonic() + 10
            blockers = []
            while time.monotonic() < deadline:
                with connections["default"].cursor() as cursor:
                    cursor.execute("SELECT pg_blocking_pids(%s)", [selecting["pid"]])
                    blockers = cursor.fetchone()[0]
                if locked["pid"] in blockers:
                    break
                time.sleep(0.025)
            self.assertIn(locked["pid"], blockers, "The second API request must wait for the same action journal row")
            one.release()
            original, recovered = one.read(), two.read()
            self.assertEqual((one.wait(), two.wait()), (0, 0))
            self.assertEqual((original["status"], recovered["status"]), (200, 200))
            self.assertEqual((original["alias"], recovered["alias"]), ("app", "app"))
            self.assertEqual(
                (original["database_user"], recovered["database_user"]),
                (settings.RLS_ROLES["app"], settings.RLS_ROLES["app"]),
            )
            self.assertEqual(original["body"], recovered["body"])
            events = [json.loads(line) for line in (directory / "events.jsonl").read_text().splitlines()]
            self.assertEqual(events, [{"event": "order_modified", "alias": "app"}])
        with use_operator():
            self.order.refresh_from_db()
            self.assertEqual((self.order.quantity, self.order.modification_count), (12, 1))
            self.assertEqual(OrderModificationLog.objects.filter(order=self.order).count(), 3)
            self.assertTrue(SigningChallenge.objects.get(digest=first["digest"]).is_consumed)
            self.assertFalse(SigningChallenge.objects.get(digest=second["digest"]).is_consumed)


@skipUnless(connection.vendor == "postgresql", "Independent action requests require PostgreSQL transactions and roles")
class OrderActionProcessTest(ActionProcessChecks, APITransactionTestCase):
    pass


class ScopedOrderActionProcessTest(RunsOnTheScopedConnection, ActionProcessChecks, APITransactionTestCase):
    pass
