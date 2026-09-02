import uuid
from contextlib import contextmanager
from datetime import timedelta
from queue import Empty, Queue
from threading import Barrier, Event, Thread
from time import monotonic, sleep
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection, connections, transaction
from django.test import RequestFactory, TransactionTestCase, override_settings
from django.utils import timezone
from procrastinate.contrib.django.models import ProcrastinateJob

from authentication.models import (
    AuthenticationChallenge,
    AuthenticationChallengeDelivery,
)
from authentication.security import (
    V2KeyMaterial,
    destination_rate_digests,
    ip_rate_digests,
    resolve_access_config,
    resolve_challenge_config,
    resolve_trusted_proxy_config,
)
from authentication.services.v2_challenge_admission import (
    V2ChallengeAdmissionError,
    _admit_challenge_delivery,
    _advisory_lock_ids,
    _record_unknown_context_ip_suppression,
    _V2ChallengeAdmissionDecision,
    _V2ChallengeAdmissionPlan,
    record_unknown_signup_context_ip_suppression,
)
from authentication.services.v2_delivery_queue import (
    _V2DeliveryQueueError,
    _validate_v2_delivery_queue,
)
from authentication.tasks import V2_DELIVERY_HOLD_QUEUE, deliver_v2_challenge
from ledova_backend.logging_filters import V2_DELIVERY_TASK_NAME
from ledova_backend.procrastinate_app import app as django_procrastinate_app

User = get_user_model()


@skipUnless(connection.vendor == "postgresql", "PostgreSQL locking semantics are required")
@override_settings(DEBUG=False, SECRET_KEY="django-secret-distinct-from-v2-admission-keys")
class V2ChallengeAdmissionPostgresTest(TransactionTestCase):
    reset_sequences = False
    error = "V2 challenge service unavailable."

    def setUp(self):
        self.clear_v2_jobs()
        self.factory = RequestFactory()
        self.key_material = V2KeyMaterial(
            access_signing_key=b"a" * 32,
            refresh_hmac_key=b"r" * 32,
        )
        self.access_configuration = resolve_access_config(self.key_material)
        self.old_configuration = self.configuration("rate-1", b"o" * 32)
        self.new_configuration = self.configuration("rate-2", b"n" * 32)

    def tearDown(self):
        self.clear_v2_jobs()
        super().tearDown()

    def clear_v2_jobs(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM procrastinate_jobs WHERE task_name = %s",
                [V2_DELIVERY_TASK_NAME],
            )

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
        return self.ip_rates_for(b"\xcb\x00\x71\x2a", configuration)

    def ip_rates_for(self, packed_network, configuration=None):
        return ip_rate_digests(
            4,
            32,
            packed_network,
            configuration=configuration or self.new_configuration,
        )

    def destination_rates(self, destination="owner@example.test", configuration=None):
        return destination_rate_digests(
            destination,
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
        return self.create_delivery_row(
            rate_key_id=alias.key_id,
            destination_rate_digest=destination_rate_digest,
            ip_rate_digest=alias.digest,
            reserved_at=reserved_at,
            purpose=purpose,
            status=status,
        )

    def create_delivery_row(
        self,
        *,
        rate_key_id,
        destination_rate_digest,
        ip_rate_digest,
        reserved_at,
        purpose="signup",
        status="suppressed",
        using="default",
    ):
        return AuthenticationChallengeDelivery.objects.using(using).create(
            challenge=None,
            purpose=purpose,
            status=status,
            rate_key_id=rate_key_id,
            destination_rate_digest=destination_rate_digest,
            ip_rate_digest=ip_rate_digest,
            proof_key_id=None,
            proof_digest=None,
            reserved_at=reserved_at,
            lease_expires_at=reserved_at + timedelta(seconds=120),
            sending_at=None,
            accepted_at=None,
            proof_expires_at=None,
            resolved_at=reserved_at,
        )

    def plan_admitted(self, _locked_scope, _context):
        return _V2ChallengeAdmissionPlan(
            status=AuthenticationChallengeDelivery.Status.SUPPRESSED,
        )

    def plan_reserved(self, _locked_scope, _context):
        return _V2ChallengeAdmissionPlan(
            status=AuthenticationChallengeDelivery.Status.RESERVED,
            challenge=_locked_scope,
        )

    def v2_jobs(self):
        return ProcrastinateJob.objects.filter(task_name=V2_DELIVERY_TASK_NAME)

    def create_open_challenge(self, at, purpose="signup"):
        user = User.objects.create_user(
            email=f"queue-owner-{uuid.uuid4()}@example.test",
            password="synthetic-test-password",
            is_active=True,
        )
        values = {
            "user": user,
            "purpose": purpose,
            "transport": AuthenticationChallenge.Transport.BROWSER,
            "status": AuthenticationChallenge.Status.OPEN,
            "pending_context_key_id": "synthetic-proof-key-1",
            "pending_context_digest": b"c" * 32,
            "target_email": None,
            "otp_failure_count": 0,
            "created_at": at - timedelta(minutes=1),
            "expires_at": at + timedelta(hours=1),
            "resolved_at": None,
        }
        if purpose == AuthenticationChallenge.Purpose.PASSWORD_RESET:
            values["pending_context_key_id"] = None
            values["pending_context_digest"] = None
        if purpose == AuthenticationChallenge.Purpose.EMAIL_CHANGE:
            values["target_email"] = f"queue-target-{uuid.uuid4()}@example.test"
        return AuthenticationChallenge.objects.create(**values)

    def call_reserved_admission(self, at, *, challenge=None, purpose="signup", **overrides):
        challenge = challenge or self.create_open_challenge(at, purpose)

        def lock_scope(using):
            return AuthenticationChallenge.objects.using(using).select_for_update().get(pk=challenge.pk)

        return self.call_admission(
            at,
            purpose=purpose,
            lock_scope=lock_scope,
            apply_admitted=self.plan_reserved,
            **overrides,
        )

    def call_admission(
        self,
        at,
        *,
        purpose="signup",
        destination_rates=None,
        ip_rates=None,
        configuration=None,
        post_lock_clock=None,
        lock_scope=None,
        apply_admitted=None,
    ):
        configuration = configuration or self.new_configuration
        return _admit_challenge_delivery(
            purpose=purpose,
            destination_rates=destination_rates or self.destination_rates(configuration=configuration),
            ip_rates=ip_rates or self.ip_rates(configuration),
            challenge_configuration=configuration,
            using="default",
            post_lock_clock=post_lock_clock or (lambda _cursor: at),
            lock_scope=lock_scope or (lambda using: using),
            apply_admitted=apply_admitted or self.plan_admitted,
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
        with connection.cursor() as cursor:
            cursor.execute("SELECT clock_timestamp()")
            before = cursor.fetchone()[0]

        result = self.call_public()

        with connection.cursor() as cursor:
            cursor.execute("SELECT clock_timestamp()")
            after = cursor.fetchone()[0]
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
        self.assertEqual(self.v2_jobs().count(), 0)

    def test_reserved_delivery_and_job_commit_together_on_the_same_connection(self):
        at = timezone.now()
        events = []
        wrappers = []

        def record(execute, sql, params, many, context):
            classification = self.classify_admission_sql(sql)
            if classification in {"insert", "enqueue"}:
                events.append(classification)
                wrapper = context["connection"]
                wrappers.append(
                    (
                        wrapper,
                        wrapper.connection,
                        wrapper.in_atomic_block,
                        wrapper.get_autocommit(),
                    )
                )
            return execute(sql, params, many, context)

        with connection.execute_wrapper(record):
            result = self.call_reserved_admission(at)

        self.assertEqual(result, _V2ChallengeAdmissionDecision.ADMITTED)
        self.assertEqual(events, ["insert", "enqueue"])
        selected = connections["default"]
        self.assertIs(wrappers[0][0], selected)
        self.assertIs(wrappers[1][0], selected)
        self.assertIsNotNone(wrappers[0][1])
        self.assertIs(wrappers[0][1], wrappers[1][1])
        self.assertEqual([item[2:] for item in wrappers], [(True, False), (True, False)])
        delivery = AuthenticationChallengeDelivery.objects.get()
        self.assertEqual(delivery.status, AuthenticationChallengeDelivery.Status.RESERVED)
        self.assertIsNone(delivery.resolved_at)
        job = self.v2_jobs().get()
        self.assertEqual(job.task_name, V2_DELIVERY_TASK_NAME)
        self.assertEqual(job.queue_name, V2_DELIVERY_HOLD_QUEUE)
        self.assertEqual(job.args, {"delivery_uuid": str(delivery.uuid)})
        self.assertEqual(job.status, "todo")
        self.assertEqual(job.priority, 0)
        self.assertEqual(job.attempts, 0)
        self.assertIsNone(job.lock)
        self.assertIsNone(job.queueing_lock)
        self.assertIsNone(job.scheduled_at)
        self.assertFalse(job.abort_requested)
        self.assertIsNone(job.worker_id)

    def test_enqueue_failure_before_and_after_sql_rolls_back_delivery_and_job(self):
        at = timezone.now()
        sensitive_value = "private-enqueue-failure-marker"

        with patch(
            "authentication.services.v2_delivery_queue.deliver_v2_challenge.defer",
            side_effect=RuntimeError(sensitive_value),
        ):
            self.assert_fixed_rejection(
                lambda: self.call_reserved_admission(at),
                sensitive_value,
            )
        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 0)
        self.assertEqual(self.v2_jobs().count(), 0)

        def fail_after_enqueue(execute, sql, params, many, context):
            result = execute(sql, params, many, context)
            if self.classify_admission_sql(sql) == "enqueue":
                raise RuntimeError(sensitive_value)
            return result

        with connection.execute_wrapper(fail_after_enqueue):
            self.assert_fixed_rejection(
                lambda: self.call_reserved_admission(at),
                sensitive_value,
            )
        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 0)
        self.assertEqual(self.v2_jobs().count(), 0)

    def test_post_enqueue_rollback_only_state_rolls_back_delivery_and_job(self):
        at = timezone.now()

        def mark_rollback(execute, sql, params, many, context):
            result = execute(sql, params, many, context)
            if self.classify_admission_sql(sql) == "enqueue":
                transaction.set_rollback(True, using="default")
            return result

        with connection.execute_wrapper(mark_rollback):
            self.assert_fixed_rejection(
                lambda: self.call_reserved_admission(at),
            )

        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 0)
        self.assertEqual(self.v2_jobs().count(), 0)

    def test_failure_after_enqueue_rolls_back_challenge_mutation_delivery_and_job(self):
        at = timezone.now()
        challenge = self.create_open_challenge(at)
        sensitive_value = "private-post-enqueue-scope-marker"

        def lock_scope(using):
            return AuthenticationChallenge.objects.using(using).select_for_update().get(pk=challenge.pk)

        def mutate_then_reserve(locked, context):
            AuthenticationChallenge.objects.using(context.using).filter(pk=locked.pk).update(otp_failure_count=1)
            return self.plan_reserved(locked, context)

        def fail_after_enqueue(execute, sql, params, many, context):
            result = execute(sql, params, many, context)
            if self.classify_admission_sql(sql) == "enqueue":
                raise RuntimeError(sensitive_value)
            return result

        with connection.execute_wrapper(fail_after_enqueue):
            self.assert_fixed_rejection(
                lambda: self.call_admission(
                    at,
                    lock_scope=lock_scope,
                    apply_admitted=mutate_then_reserve,
                ),
                sensitive_value,
            )

        challenge.refresh_from_db()
        self.assertEqual(challenge.otp_failure_count, 0)
        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 0)
        self.assertEqual(self.v2_jobs().count(), 0)

    def test_suppressed_admission_is_independent_of_queue_availability(self):
        at = timezone.now()
        manager = deliver_v2_challenge.blueprint.job_manager

        with (
            patch.object(manager, "connector", object()),
            patch.object(deliver_v2_challenge, "defer", side_effect=AssertionError) as defer,
        ):
            result = self.call_admission(at)

        self.assertEqual(result, _V2ChallengeAdmissionDecision.ADMITTED)
        self.assertEqual(
            AuthenticationChallengeDelivery.objects.get().status,
            AuthenticationChallengeDelivery.Status.SUPPRESSED,
        )
        self.assertEqual(self.v2_jobs().count(), 0)
        defer.assert_not_called()

    def test_reserved_plan_requires_a_live_matching_saved_challenge_and_destination(self):
        at = timezone.now()
        wrong_purpose = self.create_open_challenge(at, AuthenticationChallenge.Purpose.PASSWORD_RESET)
        closed = self.create_open_challenge(at)
        AuthenticationChallenge.objects.filter(pk=closed.pk).update(
            status=AuthenticationChallenge.Status.CONSUMED,
            resolved_at=at,
        )
        closed.refresh_from_db()
        expired = self.create_open_challenge(at)
        AuthenticationChallenge.objects.filter(pk=expired.pk).update(expires_at=at)
        expired.refresh_from_db()
        unsaved_user = User.objects.create_user(
            email=f"unsaved-queue-owner-{uuid.uuid4()}@example.test",
            password="synthetic-test-password",
            is_active=True,
        )
        unsaved = AuthenticationChallenge(
            user=unsaved_user,
            purpose=AuthenticationChallenge.Purpose.SIGNUP,
            transport=AuthenticationChallenge.Transport.BROWSER,
            status=AuthenticationChallenge.Status.OPEN,
            pending_context_key_id="synthetic-proof-key-1",
            pending_context_digest=b"c" * 32,
            target_email=None,
            otp_failure_count=0,
            created_at=at - timedelta(minutes=1),
            expires_at=at + timedelta(hours=1),
            resolved_at=None,
        )

        for challenge in (wrong_purpose, closed, expired, unsaved):
            with self.subTest(challenge_state=challenge.status, saved=not challenge._state.adding):
                self.assert_fixed_rejection(
                    lambda challenge=challenge: self.call_admission(
                        at,
                        lock_scope=lambda _using: challenge,
                        apply_admitted=self.plan_reserved,
                    )
                )
                self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 0)
                self.assertEqual(self.v2_jobs().count(), 0)

        valid = self.create_open_challenge(at)
        self.assert_fixed_rejection(
            lambda: _admit_challenge_delivery(
                purpose=AuthenticationChallengeDelivery.Purpose.SIGNUP,
                destination_rates=None,
                ip_rates=self.ip_rates(),
                challenge_configuration=self.new_configuration,
                using="default",
                post_lock_clock=lambda _cursor: at,
                lock_scope=lambda _using: valid,
                apply_admitted=self.plan_reserved,
            )
        )
        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 0)
        self.assertEqual(self.v2_jobs().count(), 0)

    def test_reserved_plan_cannot_substitute_a_different_challenge_from_the_locked_scope(self):
        at = timezone.now()
        locked = self.create_open_challenge(at)
        substitute = self.create_open_challenge(at)

        def lock_scope(using):
            return AuthenticationChallenge.objects.using(using).select_for_update().get(pk=locked.pk)

        def substitute_plan(_locked_scope, _context):
            return _V2ChallengeAdmissionPlan(
                status=AuthenticationChallengeDelivery.Status.RESERVED,
                challenge=substitute,
            )

        self.assert_fixed_rejection(
            lambda: self.call_admission(
                at,
                lock_scope=lock_scope,
                apply_admitted=substitute_plan,
            )
        )
        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 0)
        self.assertEqual(self.v2_jobs().count(), 0)

    def test_kernel_owns_the_challenge_row_lock_before_the_database_clock(self):
        at = timezone.now()
        challenge = self.create_open_challenge(at)
        events = []

        def record(execute, sql, params, many, context):
            classification = self.classify_admission_sql(sql)
            if classification in {"lock_scope", "clock"}:
                events.append(classification)
            return execute(sql, params, many, context)

        def post_lock_clock(cursor):
            cursor.execute("SELECT clock_timestamp()")
            return cursor.fetchone()[0]

        with connection.execute_wrapper(record):
            result = self.call_admission(
                at,
                lock_scope=lambda _using: challenge,
                post_lock_clock=post_lock_clock,
                apply_admitted=self.plan_reserved,
            )

        self.assertEqual(result, _V2ChallengeAdmissionDecision.ADMITTED)
        self.assertEqual(events, ["lock_scope", "clock"])
        self.assertEqual(AuthenticationChallengeDelivery.objects.get().challenge_id, challenge.pk)
        self.assertEqual(self.v2_jobs().count(), 1)

    def test_reserved_plan_rechecks_the_locked_challenge_database_state(self):
        at = timezone.now()
        challenge = self.create_open_challenge(at)

        def lock_scope(using):
            return AuthenticationChallenge.objects.using(using).select_for_update().get(pk=challenge.pk)

        def close_then_return(locked, context):
            AuthenticationChallenge.objects.using(context.using).filter(pk=locked.pk).update(
                status=AuthenticationChallenge.Status.CONSUMED,
                resolved_at=context.reserved_at,
            )
            return self.plan_reserved(locked, context)

        self.assert_fixed_rejection(
            lambda: self.call_admission(
                at,
                lock_scope=lock_scope,
                apply_admitted=close_then_return,
            )
        )
        challenge.refresh_from_db()
        self.assertEqual(challenge.status, AuthenticationChallenge.Status.OPEN)
        self.assertIsNone(challenge.resolved_at)
        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 0)
        self.assertEqual(self.v2_jobs().count(), 0)

    def test_queue_binding_mismatch_rejects_before_delivery_or_enqueue_sql(self):
        at = timezone.now()
        events = []

        def record(execute, sql, params, many, context):
            events.append(self.classify_admission_sql(sql))
            return execute(sql, params, many, context)

        manager = deliver_v2_challenge.blueprint.job_manager
        with (
            patch.object(manager, "connector", object()),
            connection.execute_wrapper(record),
        ):
            self.assert_fixed_rejection(lambda: self.call_reserved_admission(at))

        self.assertNotIn("insert", events)
        self.assertNotIn("enqueue", events)
        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 0)
        self.assertEqual(self.v2_jobs().count(), 0)

    def test_queue_validator_rejects_raw_connection_and_alias_mismatch(self):
        selected = connections["default"]

        with transaction.atomic():
            for action in (
                lambda: _validate_v2_delivery_queue(
                    selected=selected,
                    raw_connection=object(),
                ),
                lambda: self._validate_with_mismatched_queue_alias(selected),
            ):
                with self.assertRaises(_V2DeliveryQueueError) as raised:
                    action()
                self.assertEqual(str(raised.exception), "V2 challenge queue unavailable.")
                self.assertIsNone(raised.exception.__cause__)
                self.assertIsNone(raised.exception.__context__)

    def _validate_with_mismatched_queue_alias(self, selected):
        with patch.object(django_procrastinate_app.connector, "alias", "private-mismatch"):
            _validate_v2_delivery_queue(
                selected=selected,
                raw_connection=selected.connection,
            )

    def test_callback_cannot_enable_query_recording_before_owned_writes(self):
        at = timezone.now()
        challenge = self.create_open_challenge(at)

        def enable_recording(_locked_scope, _context):
            connection.force_debug_cursor = True
            return _V2ChallengeAdmissionPlan(
                status=AuthenticationChallengeDelivery.Status.RESERVED,
                challenge=challenge,
            )

        try:
            self.assert_fixed_rejection(
                lambda: self.call_admission(
                    at,
                    lock_scope=lambda _using: challenge,
                    apply_admitted=enable_recording,
                )
            )
        finally:
            connection.force_debug_cursor = False

        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 0)
        self.assertEqual(self.v2_jobs().count(), 0)

    def test_delivery_insert_cannot_enable_query_recording_before_enqueue(self):
        at = timezone.now()
        events = []

        def enable_after_insert(execute, sql, params, many, context):
            result = execute(sql, params, many, context)
            classification = self.classify_admission_sql(sql)
            events.append(classification)
            if classification == "insert":
                connection.force_debug_cursor = True
            return result

        try:
            with connection.execute_wrapper(enable_after_insert):
                self.assert_fixed_rejection(lambda: self.call_reserved_admission(at))
            self.assertEqual([query["sql"] for query in connection.queries], ["ROLLBACK"])
        finally:
            connection.force_debug_cursor = False
            connection.queries_log.clear()

        self.assertNotIn("enqueue", events)
        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 0)
        self.assertEqual(self.v2_jobs().count(), 0)

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

    def test_destination_fifth_slot_is_admitted_and_sixth_is_refused(self):
        at = timezone.now()
        destination_rates = self.destination_rates()
        unrelated_ip = self.ip_rates_for(b"\xcb\x00\x71\x63").current
        for _ in range(4):
            self.create_delivery_row(
                rate_key_id=destination_rates.current.key_id,
                destination_rate_digest=destination_rates.current.digest,
                ip_rate_digest=unrelated_ip.digest,
                reserved_at=at - timedelta(minutes=1),
            )

        self.assertEqual(
            self.call_admission(at, destination_rates=destination_rates),
            _V2ChallengeAdmissionDecision.ADMITTED,
        )
        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 5)

        self.assertEqual(
            self.call_admission(at + timedelta(seconds=1), destination_rates=destination_rates),
            _V2ChallengeAdmissionDecision.REFUSED,
        )
        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 5)

    def test_password_reset_third_slot_is_admitted_and_fourth_is_refused(self):
        at = timezone.now()
        destination_rates = self.destination_rates()
        unrelated_ip = self.ip_rates_for(b"\xcb\x00\x71\x63").current
        for _ in range(2):
            self.create_delivery_row(
                rate_key_id=destination_rates.current.key_id,
                destination_rate_digest=destination_rates.current.digest,
                ip_rate_digest=unrelated_ip.digest,
                reserved_at=at - timedelta(minutes=1),
                purpose="password_reset",
            )

        self.assertEqual(
            self.call_admission(
                at,
                purpose="password_reset",
                destination_rates=destination_rates,
            ),
            _V2ChallengeAdmissionDecision.ADMITTED,
        )
        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 3)

        self.assertEqual(
            self.call_admission(
                at + timedelta(seconds=1),
                purpose="password_reset",
                destination_rates=destination_rates,
            ),
            _V2ChallengeAdmissionDecision.REFUSED,
        )
        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 3)

    def test_ip_twentieth_slot_is_admitted_and_twenty_first_is_refused(self):
        at = timezone.now()
        ip_rates = self.ip_rates()
        unrelated_destination = self.destination_rates("unrelated@example.test").current
        for _ in range(19):
            self.create_delivery_row(
                rate_key_id=ip_rates.current.key_id,
                destination_rate_digest=unrelated_destination.digest,
                ip_rate_digest=ip_rates.current.digest,
                reserved_at=at - timedelta(minutes=1),
            )

        self.assertEqual(
            self.call_admission(at, ip_rates=ip_rates),
            _V2ChallengeAdmissionDecision.ADMITTED,
        )
        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 20)

        self.assertEqual(
            self.call_admission(at + timedelta(seconds=1), ip_rates=ip_rates),
            _V2ChallengeAdmissionDecision.REFUSED,
        )
        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 20)

    def test_destination_window_counts_future_statuses_and_all_purposes(self):
        at = timezone.now()
        destination_rates = self.destination_rates()
        unrelated_ip = self.ip_rates_for(b"\xcb\x00\x71\x63").current
        rows = (
            ("signup", "suppressed", at - timedelta(minutes=1)),
            ("email_change", "abandoned", at - timedelta(minutes=2)),
            ("password_reset", "invalidated", at - timedelta(minutes=3)),
            ("email_change", "superseded", at + timedelta(minutes=1)),
            ("signup", "expired", at - timedelta(seconds=3600)),
        )
        for purpose, status, reserved_at in rows:
            self.create_delivery_row(
                rate_key_id=destination_rates.current.key_id,
                destination_rate_digest=destination_rates.current.digest,
                ip_rate_digest=unrelated_ip.digest,
                reserved_at=reserved_at,
                purpose=purpose,
                status=status,
            )

        self.assertEqual(
            self.call_admission(at, destination_rates=destination_rates),
            _V2ChallengeAdmissionDecision.ADMITTED,
        )
        self.assertEqual(
            self.call_admission(at + timedelta(seconds=1), destination_rates=destination_rates),
            _V2ChallengeAdmissionDecision.REFUSED,
        )
        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 6)

    def test_destination_window_has_no_upper_bound_and_excludes_exact_lower_bound(self):
        at = timezone.now()
        destination_rates = self.destination_rates()
        unrelated_ip = self.ip_rates_for(b"\xcb\x00\x71\x63").current
        future_shapes = (
            ("signup", "abandoned"),
            ("email_change", "superseded"),
            ("password_reset", "invalidated"),
            ("signup", "expired"),
            ("email_change", "suppressed"),
        )
        for purpose, status in future_shapes:
            self.create_delivery_row(
                rate_key_id=destination_rates.current.key_id,
                destination_rate_digest=destination_rates.current.digest,
                ip_rate_digest=unrelated_ip.digest,
                reserved_at=at + timedelta(minutes=1),
                purpose=purpose,
                status=status,
            )

        self.assertEqual(
            self.call_admission(at, destination_rates=destination_rates),
            _V2ChallengeAdmissionDecision.REFUSED,
        )
        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 5)

        AuthenticationChallengeDelivery.objects.all().delete()
        for _ in range(4):
            self.create_delivery_row(
                rate_key_id=destination_rates.current.key_id,
                destination_rate_digest=destination_rates.current.digest,
                ip_rate_digest=unrelated_ip.digest,
                reserved_at=at - timedelta(minutes=1),
            )
        self.create_delivery_row(
            rate_key_id=destination_rates.current.key_id,
            destination_rate_digest=destination_rates.current.digest,
            ip_rate_digest=unrelated_ip.digest,
            reserved_at=at - timedelta(seconds=3600),
            status="expired",
        )

        self.assertEqual(
            self.call_admission(at, destination_rates=destination_rates),
            _V2ChallengeAdmissionDecision.ADMITTED,
        )
        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 6)

    def test_reset_window_has_no_upper_bound_and_excludes_exact_lower_bound(self):
        at = timezone.now()
        destination_rates = self.destination_rates()
        unrelated_ip = self.ip_rates_for(b"\xcb\x00\x71\x63").current
        for status in ("abandoned", "expired", "invalidated"):
            self.create_delivery_row(
                rate_key_id=destination_rates.current.key_id,
                destination_rate_digest=destination_rates.current.digest,
                ip_rate_digest=unrelated_ip.digest,
                reserved_at=at + timedelta(minutes=1),
                purpose="password_reset",
                status=status,
            )

        self.assertEqual(
            self.call_admission(
                at,
                purpose="password_reset",
                destination_rates=destination_rates,
            ),
            _V2ChallengeAdmissionDecision.REFUSED,
        )
        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 3)

        AuthenticationChallengeDelivery.objects.all().delete()
        for status in ("abandoned", "invalidated"):
            self.create_delivery_row(
                rate_key_id=destination_rates.current.key_id,
                destination_rate_digest=destination_rates.current.digest,
                ip_rate_digest=unrelated_ip.digest,
                reserved_at=at - timedelta(minutes=1),
                purpose="password_reset",
                status=status,
            )
        self.create_delivery_row(
            rate_key_id=destination_rates.current.key_id,
            destination_rate_digest=destination_rates.current.digest,
            ip_rate_digest=unrelated_ip.digest,
            reserved_at=at - timedelta(seconds=3600),
            purpose="password_reset",
            status="expired",
        )

        self.assertEqual(
            self.call_admission(
                at,
                purpose="password_reset",
                destination_rates=destination_rates,
            ),
            _V2ChallengeAdmissionDecision.ADMITTED,
        )
        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 4)

    def test_ip_window_counts_future_statuses_and_all_purposes(self):
        at = timezone.now()
        ip_rates = self.ip_rates()
        unrelated_destination = self.destination_rates("unrelated@example.test").current
        shapes = (
            ("signup", "suppressed"),
            ("signup", "abandoned"),
            ("signup", "expired"),
            ("signup", "invalidated"),
            ("email_change", "suppressed"),
            ("email_change", "abandoned"),
            ("email_change", "superseded"),
            ("email_change", "expired"),
            ("email_change", "invalidated"),
            ("password_reset", "suppressed"),
            ("password_reset", "abandoned"),
            ("password_reset", "expired"),
            ("password_reset", "invalidated"),
        )
        for index in range(18):
            purpose, status = shapes[index % len(shapes)]
            self.create_delivery_row(
                rate_key_id=ip_rates.current.key_id,
                destination_rate_digest=unrelated_destination.digest,
                ip_rate_digest=ip_rates.current.digest,
                reserved_at=at - timedelta(minutes=1),
                purpose=purpose,
                status=status,
            )
        self.create_delivery_row(
            rate_key_id=ip_rates.current.key_id,
            destination_rate_digest=unrelated_destination.digest,
            ip_rate_digest=ip_rates.current.digest,
            reserved_at=at + timedelta(minutes=1),
            purpose="email_change",
            status="superseded",
        )
        self.create_delivery_row(
            rate_key_id=ip_rates.current.key_id,
            destination_rate_digest=unrelated_destination.digest,
            ip_rate_digest=ip_rates.current.digest,
            reserved_at=at - timedelta(seconds=3600),
            purpose="password_reset",
            status="invalidated",
        )

        self.assertEqual(
            self.call_admission(at, ip_rates=ip_rates),
            _V2ChallengeAdmissionDecision.ADMITTED,
        )
        self.assertEqual(
            self.call_admission(at + timedelta(seconds=1), ip_rates=ip_rates),
            _V2ChallengeAdmissionDecision.REFUSED,
        )
        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 21)

    def test_rotation_uses_exact_digest_pairs_and_current_writer_context(self):
        at = timezone.now()
        destination_rates = self.destination_rates()
        ip_rates = self.ip_rates()
        destination_old, destination_current = destination_rates.aliases
        ip_old, ip_current = ip_rates.aliases
        unrelated_destination_old = self.destination_rates("unrelated@example.test").aliases[0]
        unrelated_ip_old = self.ip_rates_for(b"\xcb\x00\x71\x63").aliases[0]
        for _ in range(4):
            self.create_delivery_row(
                rate_key_id=destination_old.key_id,
                destination_rate_digest=destination_old.digest,
                ip_rate_digest=unrelated_ip_old.digest,
                reserved_at=at - timedelta(minutes=1),
            )
        for _ in range(19):
            self.create_delivery_row(
                rate_key_id=ip_old.key_id,
                destination_rate_digest=unrelated_destination_old.digest,
                ip_rate_digest=ip_old.digest,
                reserved_at=at - timedelta(minutes=1),
            )
        self.create_delivery_row(
            rate_key_id=destination_old.key_id,
            destination_rate_digest=destination_current.digest,
            ip_rate_digest=unrelated_ip_old.digest,
            reserved_at=at - timedelta(minutes=1),
        )
        self.create_delivery_row(
            rate_key_id=ip_old.key_id,
            destination_rate_digest=unrelated_destination_old.digest,
            ip_rate_digest=ip_current.digest,
            reserved_at=at - timedelta(minutes=1),
        )
        scope = object()
        captured = []

        def apply_admitted(locked_scope, context):
            captured.append((locked_scope, context))
            return self.plan_admitted(locked_scope, context)

        self.assertEqual(
            self.call_admission(
                at,
                destination_rates=destination_rates,
                ip_rates=ip_rates,
                lock_scope=lambda _using: scope,
                apply_admitted=apply_admitted,
            ),
            _V2ChallengeAdmissionDecision.ADMITTED,
        )
        self.assertEqual(len(captured), 1)
        locked_scope, context = captured[0]
        self.assertIs(locked_scope, scope)
        self.assertEqual(context.rate_key_id, destination_current.key_id)
        self.assertEqual(context.destination_rate_digest, destination_current.digest)
        self.assertEqual(context.ip_rate_digest, ip_current.digest)
        inserted = AuthenticationChallengeDelivery.objects.get(reserved_at=at)
        self.assertEqual(inserted.uuid, context.delivery_id)
        self.assertEqual(inserted.rate_key_id, destination_current.key_id)
        self.assertEqual(bytes(inserted.destination_rate_digest), destination_current.digest)
        self.assertEqual(bytes(inserted.ip_rate_digest), ip_current.digest)

        self.assertEqual(
            self.call_admission(
                at + timedelta(seconds=1),
                destination_rates=destination_rates,
                ip_rates=ip_rates,
            ),
            _V2ChallengeAdmissionDecision.REFUSED,
        )
        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 26)

    def test_callback_and_insert_failures_roll_back_with_fixed_errors(self):
        at = timezone.now()
        sensitive_value = "private-callback-failure-marker"

        def insert_then_fail(locked_scope, context):
            self.create_delivery_row(
                rate_key_id=context.rate_key_id,
                destination_rate_digest=context.destination_rate_digest,
                ip_rate_digest=context.ip_rate_digest,
                reserved_at=context.reserved_at,
                purpose=context.purpose,
                using=context.using,
            )
            raise RuntimeError(sensitive_value)

        self.assert_fixed_rejection(
            lambda: self.call_admission(at, apply_admitted=insert_then_fail),
            sensitive_value,
        )
        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 0)

        def fail_insert(_locked_scope, context):
            self.create_delivery_row(
                rate_key_id=context.rate_key_id,
                destination_rate_digest=context.destination_rate_digest,
                ip_rate_digest=b"i" * 31,
                reserved_at=context.reserved_at,
                purpose=context.purpose,
                using=context.using,
            )

        self.assert_fixed_rejection(lambda: self.call_admission(at, apply_admitted=fail_insert))
        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 0)

    def test_callback_requires_a_valid_plan_and_cannot_cancel_the_transaction(self):
        at = timezone.now()

        def rollback_only(_locked_scope, context):
            transaction.set_rollback(True, using=context.using)
            return self.plan_admitted(_locked_scope, context)

        callbacks = (
            lambda _scope, _context: None,
            lambda _scope, _context: object(),
            lambda _scope, _context: _V2ChallengeAdmissionPlan(status="active"),
            lambda _scope, _context: _V2ChallengeAdmissionPlan(status="reserved"),
            rollback_only,
        )
        for callback in callbacks:
            with self.subTest(callback=callback):
                self.assert_fixed_rejection(lambda callback=callback: self.call_admission(at, apply_admitted=callback))
                self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 0)

    def test_atomic_exit_failure_rolls_back_and_is_fixed_unchained(self):
        at = timezone.now()
        sensitive_value = "private-atomic-exit-failure-marker"
        real_atomic = transaction.atomic

        @contextmanager
        def failing_atomic(*args, **kwargs):
            with real_atomic(*args, **kwargs):
                yield
                raise RuntimeError(sensitive_value)

        with patch("authentication.services.v2_challenge_admission.transaction.atomic", new=failing_atomic):
            self.assert_fixed_rejection(lambda: self.call_admission(at), sensitive_value)

        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 0)

    def test_reserved_atomic_exit_failure_rolls_back_delivery_and_job(self):
        at = timezone.now()
        sensitive_value = "private-reserved-atomic-exit-marker"
        real_atomic = transaction.atomic

        @contextmanager
        def failing_atomic(*args, **kwargs):
            with real_atomic(*args, **kwargs):
                yield
                raise RuntimeError(sensitive_value)

        with patch("authentication.services.v2_challenge_admission.transaction.atomic", new=failing_atomic):
            self.assert_fixed_rejection(
                lambda: self.call_reserved_admission(at),
                sensitive_value,
            )

        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 0)
        self.assertEqual(self.v2_jobs().count(), 0)

    def test_post_insert_rollback_only_state_is_fixed_and_not_admitted(self):
        at = timezone.now()

        def mark_rollback(execute, sql, params, many, context):
            result = execute(sql, params, many, context)
            if self.classify_admission_sql(sql) == "insert":
                transaction.set_rollback(True, using="default")
            return result

        with connection.execute_wrapper(mark_rollback):
            self.assert_fixed_rejection(lambda: self.call_admission(at))

        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 0)

    def classify_admission_sql(self, sql):
        normalized = " ".join(sql.split()).upper()
        if normalized.startswith("SET TRANSACTION ISOLATION LEVEL READ COMMITTED, NOT DEFERRABLE"):
            return "isolation"
        if "PG_ADVISORY_XACT_LOCK" in normalized:
            return "lock"
        if "CLOCK_TIMESTAMP" in normalized:
            return "clock"
        if normalized.startswith("SELECT") and "FOR UPDATE" in normalized:
            return "lock_scope"
        if normalized.startswith("SELECT COUNT("):
            if '"DESTINATION_RATE_DIGEST"' in normalized:
                if '"PURPOSE"' in normalized:
                    return "reset_count"
                return "destination_count"
            if '"IP_RATE_DIGEST"' in normalized:
                return "ip_count"
        if normalized.startswith('INSERT INTO "AUTHENTICATION_CHALLENGE_DELIVERY"'):
            return "insert"
        if "PROCRASTINATE_DEFER_JOBS_V1" in normalized:
            return "enqueue"
        return "other"

    def test_kernel_sql_order_uses_all_locks_then_scope_clock_counts_and_apply(self):
        events = []
        lock_parameters = []
        count_sql = {}
        destination_rates = self.destination_rates()
        ip_rates = self.ip_rates()
        scope_row = self.create_delivery_row(
            rate_key_id=destination_rates.current.key_id,
            destination_rate_digest=self.destination_rates("scope@example.test").current.digest,
            ip_rate_digest=self.ip_rates_for(b"\xcb\x00\x71\x63").current.digest,
            reserved_at=timezone.now() - timedelta(hours=2),
        )

        def record(execute, sql, params, many, context):
            classification = self.classify_admission_sql(sql)
            if classification != "other":
                events.append(classification)
            if classification == "lock":
                lock_parameters.append(params[0])
            if classification.endswith("_count"):
                count_sql[classification] = " ".join(sql.split()).upper()
            return execute(sql, params, many, context)

        def lock_scope(using):
            return AuthenticationChallengeDelivery.objects.using(using).select_for_update().get(pk=scope_row.pk)

        def post_lock_clock(cursor):
            cursor.execute("SELECT clock_timestamp()")
            return cursor.fetchone()[0]

        def apply_admitted(locked_scope, context):
            events.append("apply")
            return self.plan_admitted(locked_scope, context)

        with connection.execute_wrapper(record):
            result = self.call_admission(
                timezone.now(),
                purpose="password_reset",
                destination_rates=destination_rates,
                ip_rates=ip_rates,
                post_lock_clock=post_lock_clock,
                lock_scope=lock_scope,
                apply_admitted=apply_admitted,
            )

        expected_locks = _advisory_lock_ids(destination_rates.aliases + ip_rates.aliases)
        self.assertEqual(result, _V2ChallengeAdmissionDecision.ADMITTED)
        self.assertEqual(lock_parameters, list(expected_locks))
        self.assertEqual(
            events,
            [
                "isolation",
                *("lock" for _ in expected_locks),
                "lock_scope",
                "clock",
                "destination_count",
                "reset_count",
                "ip_count",
                "apply",
                "insert",
            ],
        )
        self.assertNotIn('"STATUS"', count_sql["destination_count"])
        self.assertNotIn('"PURPOSE"', count_sql["destination_count"])
        self.assertNotIn('"STATUS"', count_sql["reset_count"])
        self.assertIn('"PURPOSE"', count_sql["reset_count"])
        self.assertNotIn('"STATUS"', count_sql["ip_count"])
        self.assertNotIn('"PURPOSE"', count_sql["ip_count"])

    def test_non_reset_admission_omits_the_reset_specific_count(self):
        counts = []

        def record(execute, sql, params, many, context):
            classification = self.classify_admission_sql(sql)
            if classification.endswith("_count"):
                counts.append(classification)
            return execute(sql, params, many, context)

        with connection.execute_wrapper(record):
            result = self.call_admission(timezone.now())

        self.assertEqual(result, _V2ChallengeAdmissionDecision.ADMITTED)
        self.assertEqual(counts, ["destination_count", "ip_count"])

    def test_scope_and_each_count_failure_are_fixed_unchained_and_write_nothing(self):
        at = timezone.now()
        sensitive_value = "private-kernel-stage-failure-marker"

        def fail_scope(_using):
            raise RuntimeError(sensitive_value)

        self.assert_fixed_rejection(
            lambda: self.call_admission(at, lock_scope=fail_scope),
            sensitive_value,
        )
        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 0)

        for target in ("destination_count", "reset_count", "ip_count"):
            with self.subTest(target=target):

                def fail_target(execute, sql, params, many, context):
                    if self.classify_admission_sql(sql) == target:
                        raise RuntimeError(sensitive_value)
                    return execute(sql, params, many, context)

                with connection.execute_wrapper(fail_target):
                    self.assert_fixed_rejection(
                        lambda: self.call_admission(at, purpose="password_reset"),
                        sensitive_value,
                    )
                self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 0)

    def test_refusal_executes_every_count_before_returning_without_apply_or_write(self):
        at = timezone.now()
        destination_rates = self.destination_rates()
        ip_rates = self.ip_rates()
        unrelated_destination = self.destination_rates("unrelated@example.test").current
        for index in range(5):
            self.create_delivery_row(
                rate_key_id=destination_rates.current.key_id,
                destination_rate_digest=destination_rates.current.digest,
                ip_rate_digest=ip_rates.current.digest,
                reserved_at=at - timedelta(minutes=1),
                purpose="password_reset" if index < 3 else "signup",
            )
        for _ in range(15):
            self.create_delivery_row(
                rate_key_id=ip_rates.current.key_id,
                destination_rate_digest=unrelated_destination.digest,
                ip_rate_digest=ip_rates.current.digest,
                reserved_at=at - timedelta(minutes=1),
            )
        counts = []
        applied = []

        def record(execute, sql, params, many, context):
            classification = self.classify_admission_sql(sql)
            if classification.endswith("_count"):
                counts.append(classification)
            return execute(sql, params, many, context)

        def apply_admitted(_locked_scope, _context):
            applied.append(True)

        before = AuthenticationChallengeDelivery.objects.count()
        with connection.execute_wrapper(record):
            result = self.call_admission(
                at,
                purpose="password_reset",
                destination_rates=destination_rates,
                ip_rates=ip_rates,
                apply_admitted=apply_admitted,
            )

        self.assertEqual(result, _V2ChallengeAdmissionDecision.REFUSED)
        self.assertEqual(counts, ["destination_count", "reset_count", "ip_count"])
        self.assertEqual(applied, [])
        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), before)

    def test_refusal_rolls_back_scope_mutation_and_discards_on_commit(self):
        at = timezone.now()
        destination_rates = self.destination_rates()
        unrelated_ip = self.ip_rates_for(b"\xcb\x00\x71\x63").current
        rows = [
            self.create_delivery_row(
                rate_key_id=destination_rates.current.key_id,
                destination_rate_digest=destination_rates.current.digest,
                ip_rate_digest=unrelated_ip.digest,
                reserved_at=at - timedelta(minutes=1),
            )
            for _ in range(5)
        ]
        committed = []
        applied = []

        def lock_scope(using):
            locked = AuthenticationChallengeDelivery.objects.using(using).select_for_update().get(pk=rows[0].pk)
            AuthenticationChallengeDelivery.objects.using(using).filter(pk=locked.pk).update(status="invalidated")
            transaction.on_commit(lambda: committed.append(True), using=using)
            return locked

        result = self.call_admission(
            at,
            destination_rates=destination_rates,
            lock_scope=lock_scope,
            apply_admitted=lambda _scope, _context: applied.append(True),
        )

        rows[0].refresh_from_db()
        self.assertEqual(result, _V2ChallengeAdmissionDecision.REFUSED)
        self.assertEqual(rows[0].status, "suppressed")
        self.assertEqual(committed, [])
        self.assertEqual(applied, [])
        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 5)

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

    def admission_worker(
        self,
        label,
        destination_rates,
        ip_rates,
        challenge_id,
        barrier,
        pids,
        outcomes,
        applied,
    ):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '10s'")
                cursor.execute("SET statement_timeout = '15s'")
                cursor.execute("SELECT pg_backend_pid()")
                pids.put((label, cursor.fetchone()[0]))
            barrier.wait(timeout=5)

            def post_lock_clock(cursor):
                cursor.execute("SELECT clock_timestamp()")
                return cursor.fetchone()[0]

            def apply_admitted(locked_scope, context):
                applied.put(label)
                if challenge_id is None:
                    return self.plan_admitted(locked_scope, context)
                return self.plan_reserved(locked_scope, context)

            def lock_scope(using):
                if challenge_id is None:
                    return using
                return AuthenticationChallenge.objects.using(using).select_for_update().get(pk=challenge_id)

            outcome = _admit_challenge_delivery(
                purpose="signup",
                destination_rates=destination_rates,
                ip_rates=ip_rates,
                challenge_configuration=self.new_configuration,
                using="default",
                post_lock_clock=post_lock_clock,
                lock_scope=lock_scope,
                apply_admitted=apply_admitted,
            )
            outcomes.put((label, outcome))
        except BaseException as exc:
            outcomes.put((label, exc))
        finally:
            close_old_connections()

    def run_admission_workers_behind_locks(self, cases, shared_aliases, challenges=None):
        barrier = Barrier(len(cases) + 1)
        pids = Queue()
        outcomes = Queue()
        applied = Queue()
        challenge_ids = [None] * len(cases) if challenges is None else [challenge.pk for challenge in challenges]
        threads = [
            Thread(
                target=self.admission_worker,
                name=f"v2-kernel-admission-{index}",
                args=(
                    str(index),
                    destination_rates,
                    ip_rates,
                    challenge_id,
                    barrier,
                    pids,
                    outcomes,
                    applied,
                ),
            )
            for index, ((destination_rates, ip_rates), challenge_id) in enumerate(zip(cases, challenge_ids))
        ]
        lock_ids = _advisory_lock_ids(shared_aliases)
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
        finally:
            if any(thread.ident is not None for thread in threads):
                results = self.finish_workers(threads, outcomes)

        applied_labels = []
        while True:
            try:
                applied_labels.append(applied.get_nowait())
            except Empty:
                break
        return results, applied_labels

    def test_concurrent_destination_final_slot_admits_exactly_one_writer(self):
        at = timezone.now() - timedelta(minutes=1)
        destination_rates = self.destination_rates()
        unrelated_ip = self.ip_rates_for(b"\xcb\x00\x71\x63").current
        for _ in range(4):
            self.create_delivery_row(
                rate_key_id=destination_rates.current.key_id,
                destination_rate_digest=destination_rates.current.digest,
                ip_rate_digest=unrelated_ip.digest,
                reserved_at=at,
            )
        cases = (
            (destination_rates, self.ip_rates_for(b"\xcb\x00\x71\x2b")),
            (destination_rates, self.ip_rates_for(b"\xcb\x00\x71\x2c")),
        )

        results, applied = self.run_admission_workers_behind_locks(cases, destination_rates.aliases)

        self.assertEqual(
            sorted(result.value for result in results.values()),
            ["admitted", "refused"],
        )
        self.assertEqual(len(applied), 1)
        self.assertEqual(results[applied[0]], _V2ChallengeAdmissionDecision.ADMITTED)
        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 5)

    def test_concurrent_reserved_final_slot_commits_exactly_one_matching_job(self):
        at = timezone.now()
        destination_rates = self.destination_rates()
        unrelated_ip = self.ip_rates_for(b"\xcb\x00\x71\x63").current
        for _ in range(4):
            self.create_delivery_row(
                rate_key_id=destination_rates.current.key_id,
                destination_rate_digest=destination_rates.current.digest,
                ip_rate_digest=unrelated_ip.digest,
                reserved_at=at - timedelta(minutes=1),
            )
        cases = (
            (destination_rates, self.ip_rates_for(b"\xcb\x00\x71\x2b")),
            (destination_rates, self.ip_rates_for(b"\xcb\x00\x71\x2c")),
        )
        challenges = (self.create_open_challenge(at), self.create_open_challenge(at))

        results, applied = self.run_admission_workers_behind_locks(
            cases,
            destination_rates.aliases,
            challenges=challenges,
        )

        self.assertEqual(sorted(result.value for result in results.values()), ["admitted", "refused"])
        self.assertEqual(len(applied), 1)
        delivery = AuthenticationChallengeDelivery.objects.get(status=AuthenticationChallengeDelivery.Status.RESERVED)
        job = self.v2_jobs().get()
        self.assertEqual(job.args, {"delivery_uuid": str(delivery.uuid)})
        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 5)
        self.assertEqual(self.v2_jobs().count(), 1)
        self.assertEqual(delivery.challenge_id, challenges[int(applied[0])].pk)

    def test_concurrent_ip_final_slot_admits_exactly_one_writer(self):
        at = timezone.now() - timedelta(minutes=1)
        ip_rates = self.ip_rates()
        unrelated_destination = self.destination_rates("unrelated@example.test").current
        for _ in range(19):
            self.create_delivery_row(
                rate_key_id=ip_rates.current.key_id,
                destination_rate_digest=unrelated_destination.digest,
                ip_rate_digest=ip_rates.current.digest,
                reserved_at=at,
            )
        cases = (
            (self.destination_rates("first@example.test"), ip_rates),
            (self.destination_rates("second@example.test"), ip_rates),
        )

        results, applied = self.run_admission_workers_behind_locks(cases, ip_rates.aliases)

        self.assertEqual(
            sorted(result.value for result in results.values()),
            ["admitted", "refused"],
        )
        self.assertEqual(len(applied), 1)
        self.assertEqual(results[applied[0]], _V2ChallengeAdmissionDecision.ADMITTED)
        self.assertEqual(AuthenticationChallengeDelivery.objects.count(), 20)

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
