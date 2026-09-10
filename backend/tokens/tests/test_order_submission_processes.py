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
from tokens.models import SigningChallenge, SwapOrder, TransferOrder
from tokens.tests.order_submission_fixtures import SubmissionFixtures


class SubmissionChild:
    def __init__(self, case, directory, phase, body):
        self.errors = tempfile.TemporaryFile(mode="w+")
        self.process = subprocess.Popen(
            [sys.executable, "-m", "tokens.tests.order_submission_worker"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.errors,
            text=True,
            env={**os.environ, "ORDER_SUBMISSION_TEST_DATABASES": json.dumps(case.worker_databases(), default=str)},
        )
        case.addCleanup(self.close)
        self.process.stdin.write(
            json.dumps({"phase": phase, "directory": str(directory), "body": body, "user_id": case.tenant.user.pk})
            + "\n"
        )
        self.process.stdin.flush()

    def read(self):
        if not select.select([self.process.stdout], [], [], 20)[0]:
            raise AssertionError("The owned submission worker did not reach its expected stage")
        line = self.process.stdout.readline()
        if not line:
            raise AssertionError(f"The owned submission worker ended before its result: {self.error_output()}")
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


class SubmissionProcessChecks(SubmissionFixtures):
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
        counter = self.counter_order()
        signed = self.signed_body()
        with use_operator():
            original_swaps = SwapOrder.objects.count()
        with tempfile.TemporaryDirectory(prefix="order-submission-crash-") as temporary:
            directory = Path(temporary)
            child = SubmissionChild(self, directory, phase, signed)
            self.assertEqual(child.wait(), -signal.SIGKILL, child.error_output())
            recovered = self.recover()
            self.assertEqual(recovered.status_code, 200, recovered.content)
            with use_operator():
                consumed = SigningChallenge.objects.get(digest=signed["digest"]).is_consumed
                counter.refresh_from_db()
                order_count = TransferOrder.objects.count()
                swap_count = SwapOrder.objects.count()
            if phase == "committed":
                self.assertEqual(recovered.json()["status"], "created")
                self.assertTrue(consumed)
                self.assertEqual(counter.filled_quantity, 10)
                self.assertEqual(order_count, self.initial_order_count + 1)
                self.assertEqual(swap_count, original_swaps + 1)
                events = [json.loads(line) for line in (directory / "events.jsonl").read_text().splitlines()]
                self.assertEqual([event["event"] for event in events], ["order_created", "order_matched"])
                self.assertTrue(all(event["alias"] == "app" for event in events))
            else:
                self.assertEqual(recovered.json()["status"], "pending")
                self.assertFalse(consumed)
                self.assertEqual(counter.filled_quantity, 0)
                self.assertEqual(order_count, self.initial_order_count)
                self.assertEqual(swap_count, original_swaps)
                self.assertFalse((directory / "events.jsonl").exists())
            retry = self.create(signed)
            self.assertEqual(retry.status_code, 200 if phase == "committed" else 201, retry.content)
            with use_operator():
                self.assertEqual(TransferOrder.objects.count(), self.initial_order_count + 1)
                self.assertEqual(SwapOrder.objects.count(), original_swaps + 1)
                self.assertTrue(SigningChallenge.objects.get(digest=signed["digest"]).is_consumed)
            self.assertEqual(self.recover().json()["order"]["uuid"], retry.json()["order"]["uuid"])

    def test_process_death_after_spend_keeps_the_pending_submission_and_unspent_challenge(self):
        self.crash("spent")

    def test_process_death_after_matching_rolls_back_orders_swaps_and_reservations(self):
        self.crash("matched")

    def test_process_death_after_commit_recovers_the_original_match_once(self):
        self.crash("committed")

    def test_independent_app_requests_for_the_same_submission_serialize_and_recover_one_result(self):
        counter = self.counter_order()
        first = self.signed_body()
        second = self.signed_body()
        with use_operator():
            original_swaps = SwapOrder.objects.count()
        with tempfile.TemporaryDirectory(prefix="order-submission-retry-") as temporary:
            directory = Path(temporary)
            one = SubmissionChild(self, directory, "pause", first)
            locked = one.read()
            self.assertEqual(locked["stage"], "locked")
            self.assertEqual(locked["database_user"], settings.RLS_ROLES["app"])
            two = SubmissionChild(self, directory, "compete", second)
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
            self.assertIn(locked["pid"], blockers, "The second API request must wait for the same submission row")
            one.release()
            original = one.read()
            recovered = two.read()
            self.assertEqual((one.wait(), two.wait()), (0, 0))
            self.assertEqual((original["status"], recovered["status"]), (201, 200))
            self.assertEqual((original["alias"], recovered["alias"]), ("app", "app"))
            self.assertEqual(
                (original["database_user"], recovered["database_user"]),
                (settings.RLS_ROLES["app"], settings.RLS_ROLES["app"]),
            )
            self.assertEqual(original["body"], recovered["body"])
            events = [json.loads(line) for line in (directory / "events.jsonl").read_text().splitlines()]
            self.assertEqual([event["event"] for event in events], ["order_created", "order_matched"])
        with use_operator():
            self.assertEqual(TransferOrder.objects.count(), self.initial_order_count + 1)
            self.assertEqual(SwapOrder.objects.count(), original_swaps + 1)
            counter.refresh_from_db()
            self.assertEqual(counter.filled_quantity, 10)
            self.assertTrue(SigningChallenge.objects.get(digest=first["digest"]).is_consumed)
            self.assertFalse(SigningChallenge.objects.get(digest=second["digest"]).is_consumed)


@skipUnless(connection.vendor == "postgresql", "Independent API requests require PostgreSQL transactions and roles")
class OrderSubmissionProcessTest(SubmissionProcessChecks, APITransactionTestCase):
    pass


class ScopedOrderSubmissionProcessTest(RunsOnTheScopedConnection, SubmissionProcessChecks, APITransactionTestCase):
    pass
