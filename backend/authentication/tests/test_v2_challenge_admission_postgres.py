from datetime import timedelta
from queue import Empty, Queue
from threading import Barrier, Event, Thread
from time import monotonic, sleep
from unittest import skipUnless
from unittest.mock import patch

from django.db import close_old_connections, connection, transaction
from django.test import RequestFactory, TransactionTestCase, override_settings
from django.utils import timezone

from authentication.models import (
    AuthenticationChallenge,
    AuthenticationChallengeDelivery,
)
from authentication.security import (
    V2KeyMaterial,
    ip_rate_digests,
    resolve_access_config,
    resolve_challenge_config,
    resolve_trusted_proxy_config,
)
from authentication.services.v2_challenge_admission import (
    V2ChallengeAdmissionError,
    _advisory_lock_ids,
    _record_unknown_context_ip_suppression,
    record_unknown_signup_context_ip_suppression,
)


@skipUnless(connection.vendor == "postgresql", "PostgreSQL locking semantics are required")
@override_settings(DEBUG=False, SECRET_KEY="django-secret-distinct-from-v2-admission-keys")
class V2ChallengeAdmissionPostgresTest(TransactionTestCase):
    reset_sequences = False
    error = "V2 challenge service unavailable."

    def setUp(self):
        self.factory = RequestFactory()
        self.key_material = V2KeyMaterial(
            access_signing_key=b"a" * 32,
            refresh_hmac_key=b"r" * 32,
        )
        self.access_configuration = resolve_access_config(self.key_material)
        self.old_configuration = self.configuration("rate-1", b"o" * 32)
        self.new_configuration = self.configuration("rate-2", b"n" * 32)

    def configuration(self, current_rate_kid, rate_key):
        return resolve_challenge_config(
            self.key_material,
            self.access_configuration,
            proof_key=b"p" * 32,
            rate_key=rate_key,
            current_rate_kid=current_rate_kid,
            rate_keys={"rate-1": b"o" * 32, "rate-2": b"n" * 32},
        )

    def ip_rates(self, configuration=None):
        return ip_rate_digests(
            4,
            32,
            b"\xcb\x00\x71\x2a",
            configuration=configuration or self.new_configuration,
        )

    def request(self):
        request = self.factory.post("/")
        request.META["REMOTE_ADDR"] = "203.0.113.42"
        request.META["HTTP_X_FORWARDED_FOR"] = "198.51.100.7"
        return request

    def call_public(self, configuration=None):
        return record_unknown_signup_context_ip_suppression(
            request=self.request(),
            trusted_proxy_configuration=resolve_trusted_proxy_config(()),
            challenge_configuration=configuration or self.new_configuration,
        )

    def call_private(self, at, configuration=None, purpose="signup"):
        configuration = configuration or self.new_configuration
        return _record_unknown_context_ip_suppression(
            purpose=purpose,
            ip_rates=self.ip_rates(configuration),
            challenge_configuration=configuration,
            using="default",
            post_lock_clock=lambda _cursor: at,
        )

    def create_rate_row(
        self,
        alias,
        reserved_at,
        *,
        purpose="signup",
        status="suppressed",
        destination_rate_digest=None,
    ):
        if purpose == "password_reset" and destination_rate_digest is None:
            destination_rate_digest = b"d" * 32
        return AuthenticationChallengeDelivery.objects.create(
            challenge=None,
            purpose=purpose,
            status=status,
            rate_key_id=alias.key_id,
            destination_rate_digest=destination_rate_digest,
            ip_rate_digest=alias.digest,
            proof_key_id=None,
            proof_digest=None,
            reserved_at=reserved_at,
            lease_expires_at=reserved_at + timedelta(seconds=120),
            sending_at=None,
            accepted_at=None,
            proof_expires_at=None,
            resolved_at=reserved_at,
        )

    def create_matching_rows(self, count, reserved_at, configuration=None):
        alias = self.ip_rates(configuration).current
        return [self.create_rate_row(alias, reserved_at) for _ in range(count)]

    def assert_fixed_rejection(self, action, sensitive_value=None):
        with self.assertRaises(V2ChallengeAdmissionError) as raised:
            action()

        exception = raised.exception
        self.assertEqual(str(exception), self.error)
        self.assertEqual(repr(exception), f"V2ChallengeAdmissionError({self.error!r})")
        self.assertEqual(exception.args, (self.error,))
        self.assertIsNone(exception.__cause__)
        self.assertIsNone(exception.__context__)
        if sensitive_value is not None:
            rendered = f"{exception!s} {exception!r} {exception.args!r}"
            self.assertNotIn(sensitive_value, rendered)

    def test_success_inserts_only_the_terminal_ip_rate_evidence_shape(self):
        before = timezone.now()

        result = self.call_public()

        after = timezone.now()
        self.assertIsNone(result)
        delivery = AuthenticationChallengeDelivery.objects.get()
        self.assertEqual(delivery.uuid.version, 4)
        self.assertIsNone(delivery.challenge_id)
        self.assertEqual(delivery.purpose, "signup")
        self.assertEqual(delivery.status, "suppressed")
        self.assertEqual(delivery.rate_key_id, self.ip_rates().current.key_id)
        self.assertIsNone(delivery.destination_rate_digest)
        self.assertEqual(bytes(delivery.ip_rate_digest), self.ip_rates().current.digest)
        self.assertIsNone(delivery.proof_key_id)
        self.assertIsNone(delivery.proof_digest)
        self.assertIsNone(delivery.sending_at)
        self.assertIsNone(delivery.accepted_at)
        self.assertIsNone(delivery.proof_expires_at)
        self.assertEqual(delivery.resolved_at, delivery.reserved_at)
        self.assertEqual(delivery.lease_expires_at - delivery.reserved_at, timedelta(seconds=120))
        self.assertGreaterEqual(delivery.reserved_at, before)
        self.assertLessEqual(delivery.reserved_at, after)
        self.assertEqual(AuthenticationChallenge.objects.count(), 0)

    def test_twentieth_is_inserted_and_twenty_first_is_refused_without_a_row(self):
        self.create_matching_rows(19, timezone.now() - timedelta(minutes=1))

        self.assertIsNone(self.call_public())
        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 20)

        self.assertIsNone(self.call_public())
        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 20)

    def test_window_excludes_the_exact_lower_boundary(self):
        at = timezone.now()
        self.create_matching_rows(19, at - timedelta(minutes=1))
        self.create_matching_rows(1, at - timedelta(seconds=3600))

        self.call_private(at)

        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 21)
        self.assertEqual(AuthenticationChallengeDelivery.objects.filter(reserved_at=at).count(), 1)

    def test_future_and_unrelated_status_and_purpose_rows_count_fail_closed(self):
        at = timezone.now()
        rates = self.ip_rates()
        self.create_matching_rows(18, at - timedelta(minutes=1))
        self.create_rate_row(rates.current, at + timedelta(minutes=1))
        self.create_rate_row(
            rates.current,
            at - timedelta(minutes=1),
            purpose="password_reset",
            status="abandoned",
        )

        self.call_private(at)

        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 20)
        self.assertFalse(AuthenticationChallengeDelivery.objects.filter(reserved_at=at).exists())

    def test_rotation_count_uses_exact_alias_pairs_and_writes_only_current(self):
        at = timezone.now()
        old, current = self.ip_rates().aliases
        for _ in range(19):
            self.create_rate_row(old, at - timedelta(minutes=1))
        self.create_rate_row(
            current,
            at - timedelta(minutes=1),
            destination_rate_digest=b"d" * 32,
        )
        AuthenticationChallengeDelivery.objects.filter(rate_key_id=current.key_id).update(rate_key_id=old.key_id)

        self.call_private(at)

        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 21)
        inserted = AuthenticationChallengeDelivery.objects.get(reserved_at=at)
        self.assertEqual(inserted.rate_key_id, current.key_id)
        self.assertEqual(bytes(inserted.ip_rate_digest), current.digest)

        self.call_private(at + timedelta(seconds=1))
        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 21)

    def classify_sql(self, sql):
        normalized = " ".join(sql.split()).upper()
        if normalized.startswith("SET TRANSACTION ISOLATION LEVEL READ COMMITTED, NOT DEFERRABLE"):
            return "isolation"
        if "PG_ADVISORY_XACT_LOCK" in normalized:
            return "lock"
        if "CLOCK_TIMESTAMP" in normalized:
            return "clock"
        if normalized.startswith("SELECT COUNT("):
            return "count"
        if normalized.startswith('INSERT INTO "AUTHENTICATION_CHALLENGE_DELIVERY"'):
            return "insert"
        return "other"

    def test_sql_order_isolation_locks_clock_count_insert_without_retaining_values(self):
        events = []

        def record(execute, sql, params, many, context):
            events.append(self.classify_sql(sql))
            return execute(sql, params, many, context)

        self.assertIs(connection.queries_logged, False)
        with connection.execute_wrapper(record):
            self.call_public()

        self.assertEqual(events, ["isolation", "lock", "lock", "clock", "count", "insert"])

    def test_database_failures_roll_back_and_replace_sensitive_details(self):
        sensitive_value = "private-database-failure-marker"

        for target in ("isolation", "lock", "clock", "count", "insert"):
            with self.subTest(target=target):

                def fail_target(execute, sql, params, many, context):
                    if self.classify_sql(sql) == target:
                        raise RuntimeError(sensitive_value)
                    return execute(sql, params, many, context)

                with connection.execute_wrapper(fail_target):
                    self.assert_fixed_rejection(self.call_public, sensitive_value)
                self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 0)

        self.call_public()
        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 1)

    def worker(self, label, configuration, barrier, pids, outcomes):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '10s'")
                cursor.execute("SET statement_timeout = '15s'")
                cursor.execute("SELECT pg_backend_pid()")
                pids.put((label, cursor.fetchone()[0]))
            barrier.wait(timeout=5)
            outcomes.put((label, self.call_public(configuration)))
        except BaseException as exc:
            outcomes.put((label, exc))
        finally:
            close_old_connections()

    def wait_until_blocked(self, pids):
        deadline = monotonic() + 5
        while monotonic() < deadline:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_blocking_pids(pid) FROM unnest(%s::int[]) AS pid",
                    [list(pids)],
                )
                blockers = [row[0] for row in cursor.fetchall()]
            if len(blockers) == len(pids) and all(blockers):
                return True
            sleep(0.01)
        return False

    def finish_workers(self, threads, outcomes):
        for thread in threads:
            thread.join(timeout=16)
            self.assertFalse(thread.is_alive(), f"{thread.name} did not finish")

        results = {}
        for _ in threads:
            try:
                label, outcome = outcomes.get(timeout=1)
            except Empty:
                self.fail("An admission worker produced no outcome")
            if isinstance(outcome, BaseException):
                raise outcome
            results[label] = outcome
        return results

    def run_workers_behind_lock(self, configurations, *, capture_marker=False):
        barrier = Barrier(len(configurations) + 1)
        pids = Queue()
        outcomes = Queue()
        threads = [
            Thread(
                target=self.worker,
                name=f"v2-admission-{index}",
                args=(str(index), configuration, barrier, pids, outcomes),
            )
            for index, configuration in enumerate(configurations)
        ]
        lock_ids = _advisory_lock_ids(self.ip_rates(configurations[0]).aliases)
        marker = None
        results = None

        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    for lock_id in lock_ids:
                        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [lock_id])
                for thread in threads:
                    thread.start()
                worker_pids = {}
                for _ in threads:
                    label, pid = pids.get(timeout=5)
                    worker_pids[label] = pid
                barrier.wait(timeout=5)
                self.assertTrue(self.wait_until_blocked(worker_pids.values()))
                if capture_marker:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT clock_timestamp()")
                        marker = cursor.fetchone()[0]
        finally:
            if any(thread.ident is not None for thread in threads):
                results = self.finish_workers(threads, outcomes)

        return results, marker

    def test_concurrent_final_slot_allows_exactly_one_insert(self):
        self.create_matching_rows(19, timezone.now() - timedelta(minutes=1))

        results, _marker = self.run_workers_behind_lock([self.new_configuration, self.new_configuration])

        self.assertEqual(results, {"0": None, "1": None})
        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 20)

    def test_rotation_writers_share_locks_and_count_both_aliases(self):
        at = timezone.now() - timedelta(minutes=1)
        old_alias = self.ip_rates(self.old_configuration).current
        for _ in range(19):
            self.create_rate_row(old_alias, at)

        results, _marker = self.run_workers_behind_lock([self.old_configuration, self.new_configuration])

        self.assertEqual(results, {"0": None, "1": None})
        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 20)
        inserted = AuthenticationChallengeDelivery.objects.order_by("-reserved_at").first()
        self.assertIn(inserted.rate_key_id, {"rate-1", "rate-2"})

    def test_waiting_transaction_uses_a_post_lock_database_timestamp(self):
        results, marker = self.run_workers_behind_lock(
            [self.new_configuration],
            capture_marker=True,
        )

        self.assertEqual(results, {"0": None})
        delivery = AuthenticationChallengeDelivery.objects.get()
        self.assertGreaterEqual(delivery.reserved_at, marker)
        self.assertEqual(delivery.resolved_at, delivery.reserved_at)
        self.assertEqual(delivery.lease_expires_at, delivery.reserved_at + timedelta(seconds=120))

    def test_older_waiter_sees_rate_evidence_committed_by_a_newer_lock_holder(self):
        at = timezone.now() - timedelta(minutes=1)
        self.create_matching_rows(19, at)
        rates = self.ip_rates()
        lock_ids = _advisory_lock_ids(rates.aliases)
        before_lock = Event()
        allow_lock = Event()
        pid_queue = Queue()
        outcome_queue = Queue()

        def older_waiter():
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '10s'")
                    cursor.execute("SET statement_timeout = '15s'")
                    cursor.execute("SET SESSION CHARACTERISTICS AS TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                    cursor.execute("SELECT pg_backend_pid()")
                    pid_queue.put(cursor.fetchone()[0])

                paused = False

                def pause_before_first_lock(execute, sql, params, many, context):
                    nonlocal paused
                    if self.classify_sql(sql) == "lock" and not paused:
                        paused = True
                        before_lock.set()
                        if not allow_lock.wait(timeout=5):
                            raise TimeoutError
                    return execute(sql, params, many, context)

                with connection.execute_wrapper(pause_before_first_lock):
                    outcome_queue.put(self.call_public())
            except BaseException as exc:
                outcome_queue.put(exc)
            finally:
                close_old_connections()

        worker = Thread(target=older_waiter, name="v2-admission-older-waiter")
        worker.start()
        inserted = None
        try:
            worker_pid = pid_queue.get(timeout=5)
            self.assertTrue(before_lock.wait(timeout=5))
            with transaction.atomic():
                with connection.cursor() as cursor:
                    for lock_id in lock_ids:
                        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [lock_id])
                allow_lock.set()
                self.assertTrue(self.wait_until_blocked([worker_pid]))
                with connection.cursor() as cursor:
                    cursor.execute("SELECT clock_timestamp()")
                    committed_at = cursor.fetchone()[0]
                inserted = self.create_rate_row(rates.current, committed_at)
        finally:
            allow_lock.set()
            worker.join(timeout=16)

        self.assertFalse(worker.is_alive())
        try:
            outcome = outcome_queue.get(timeout=1)
        except Empty:
            self.fail("The older admission worker produced no outcome")
        if isinstance(outcome, BaseException):
            raise outcome
        self.assertIsNone(outcome)
        self.assertIsNotNone(inserted)
        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 20)
        self.assertTrue(AuthenticationChallengeDelivery.objects.filter(pk=inserted.pk).exists())

    def test_nested_transaction_is_rejected_without_a_delivery(self):
        with transaction.atomic():
            self.assert_fixed_rejection(self.call_public)

        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 0)

    def test_manual_transaction_mode_is_rejected_before_a_delivery(self):
        transaction.set_autocommit(False)
        try:
            self.assert_fixed_rejection(self.call_public)
        finally:
            transaction.rollback()
            transaction.set_autocommit(True)

        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 0)

    def test_service_enforces_read_committed_over_a_repeatable_read_session_default(self):
        observed = []

        def inspect_clock(cursor):
            cursor.execute("SHOW transaction_isolation")
            observed.append(cursor.fetchone()[0])
            cursor.execute("SELECT clock_timestamp()")
            return cursor.fetchone()[0]

        with connection.cursor() as cursor:
            cursor.execute("SET SESSION CHARACTERISTICS AS TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        try:
            with patch(
                "authentication.services.v2_challenge_admission._database_clock",
                inspect_clock,
            ):
                self.call_public()
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SET SESSION CHARACTERISTICS AS TRANSACTION ISOLATION LEVEL READ COMMITTED")

        self.assertEqual(observed, ["read committed"])
        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 1)

    def test_invalid_clock_rolls_back_with_a_fixed_error(self):
        sensitive_value = "private-clock-value-marker"
        with patch(
            "authentication.services.v2_challenge_admission._database_clock",
            return_value=sensitive_value,
        ):
            self.assert_fixed_rejection(self.call_public, sensitive_value)

        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 0)
