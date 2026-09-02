import uuid
from contextlib import contextmanager
from datetime import timedelta
from queue import Empty, Queue
from threading import Barrier, Event, Thread
from time import monotonic, sleep
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from authentication.models import AuthSession, RefreshCredential
from authentication.security import (
    V2KeyMaterial,
    encode_v2_refresh_token,
    refresh_secret_digest,
)
from authentication.services.v2_sessions import (
    BrowserRefreshRaced,
    RefreshRotated,
    SessionRejected,
    rotate_browser_refresh,
    rotate_native_refresh,
)

User = get_user_model()


@skipUnless(connection.vendor == "postgresql", "PostgreSQL locking semantics are required")
class V2SessionServicePostgresTest(TransactionTestCase):
    reset_sequences = False

    def setUp(self):
        self.now = timezone.now()
        self.key_material = V2KeyMaterial(
            access_signing_key=b"a" * 32,
            refresh_hmac_key=b"r" * 32,
        )
        self.user = User.objects.create_user(
            email="refresh-race@example.test",
            password="test-password-123",
            is_active=True,
            is_email_verified=True,
        )

    def create_refresh(self, client_type):
        session = AuthSession.objects.create(
            user=self.user,
            client_type=client_type,
            absolute_expires_at=self.now + timedelta(days=30),
            last_used_at=self.now,
        )
        selector = uuid.uuid4()
        secret = b"s" * 32
        credential = RefreshCredential.objects.create(
            uuid=selector,
            session=session,
            secret_digest=refresh_secret_digest(
                selector,
                secret,
                self.key_material.refresh_hmac_key,
            ),
            expires_at=self.now + timedelta(days=7),
        )
        return session, credential, encode_v2_refresh_token(selector, secret)

    def rotate(self, operation, token):
        return operation(
            token,
            clock=lambda: self.now,
            key_material=self.key_material,
        )

    def worker(self, label, operation, token, barrier, started, pids, outcomes):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '10s'")
                cursor.execute("SET statement_timeout = '15s'")
                cursor.execute("SELECT pg_backend_pid()")
                pid = cursor.fetchone()[0]
            pids.put((label, pid))
            barrier.wait(timeout=5)
            started.set()
            outcomes.put((label, self.rotate(operation, token)))
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

    def finish_workers(self, run):
        for thread in run["threads"]:
            thread.join(timeout=16)
        for thread in run["threads"]:
            self.assertFalse(thread.is_alive(), f"{thread.name} did not finish")

        results = {}
        for _ in run["threads"]:
            try:
                label, outcome = run["outcomes"].get(timeout=1)
            except Empty:
                self.fail("A refresh worker produced no outcome")
            if isinstance(outcome, BaseException):
                raise outcome
            results[label] = outcome
        return results

    @contextmanager
    def workers_blocked_by(self, hold_lock, calls):
        barrier = Barrier(len(calls) + 1)
        pids = Queue()
        outcomes = Queue()
        started = {label: Event() for label, _operation, _token in calls}
        threads = [
            Thread(
                target=self.worker,
                name=f"v2-refresh-{label}",
                args=(label, operation, token, barrier, started[label], pids, outcomes),
            )
            for label, operation, token in calls
        ]
        run = {"threads": threads, "outcomes": outcomes}

        try:
            with transaction.atomic():
                hold_lock()
                for thread in threads:
                    thread.start()

                worker_pids = {}
                for _ in threads:
                    label, pid = pids.get(timeout=5)
                    worker_pids[label] = pid

                barrier.wait(timeout=5)
                for event in started.values():
                    self.assertTrue(event.wait(timeout=5))
                self.assertTrue(self.wait_until_blocked(worker_pids.values()))
                run["pids"] = worker_pids
                yield run
        finally:
            if any(thread.ident is not None for thread in threads):
                run["results"] = self.finish_workers(run)

    def test_simultaneous_native_rotation_creates_one_successor_then_revokes_on_replay(self):
        session, predecessor, token = self.create_refresh(AuthSession.ClientType.NATIVE)
        calls = [
            ("first", rotate_native_refresh, token),
            ("second", rotate_native_refresh, token),
        ]

        with self.workers_blocked_by(
            lambda: User.objects.select_for_update().get(pk=self.user.pk),
            calls,
        ) as run:
            pass

        results = run["results"]
        self.assertCountEqual([result.code for result in results.values()], ["refresh_rotated", "refresh_reused"])
        self.assertEqual(sum(isinstance(result, RefreshRotated) for result in results.values()), 1)
        self.assertEqual(sum(isinstance(result, SessionRejected) for result in results.values()), 1)

        session.refresh_from_db()
        predecessor.refresh_from_db()
        self.assertEqual(session.status, AuthSession.Status.REVOKED)
        self.assertEqual(session.revoke_reason, AuthSession.RevokeReason.REFRESH_REUSED)
        self.assertIsNotNone(predecessor.replaced_by_id)
        self.assertEqual(RefreshCredential.objects.filter(session=session).count(), 2)
        self.assertEqual(
            RefreshCredential.objects.filter(session=session, revoked_at__isnull=True).count(),
            0,
        )

    def test_simultaneous_browser_rotation_creates_one_successor_and_one_confirmation(self):
        session, predecessor, token = self.create_refresh(AuthSession.ClientType.BROWSER)
        calls = [
            ("first", rotate_browser_refresh, token),
            ("second", rotate_browser_refresh, token),
        ]

        with self.workers_blocked_by(
            lambda: User.objects.select_for_update().get(pk=self.user.pk),
            calls,
        ) as run:
            pass

        results = run["results"]
        self.assertCountEqual([result.code for result in results.values()], ["refresh_rotated", "refresh_raced"])
        self.assertEqual(sum(isinstance(result, RefreshRotated) for result in results.values()), 1)
        self.assertEqual(sum(isinstance(result, BrowserRefreshRaced) for result in results.values()), 1)

        session.refresh_from_db()
        predecessor.refresh_from_db()
        self.assertEqual(session.status, AuthSession.Status.REFRESH_CONFIRMATION_REQUIRED)
        self.assertIsNotNone(predecessor.replaced_by_id)
        self.assertIsNotNone(predecessor.confirmation_nonce_digest)
        self.assertEqual(RefreshCredential.objects.filter(session=session).count(), 2)
        self.assertEqual(
            RefreshCredential.objects.filter(
                session=session,
                confirmation_nonce_digest__isnull=False,
            ).count(),
            1,
        )

    def test_simultaneous_valid_and_wrong_secret_rotate_once_without_revocation(self):
        session, predecessor, token = self.create_refresh(AuthSession.ClientType.NATIVE)
        wrong_token = encode_v2_refresh_token(predecessor.uuid, b"x" * 32)
        calls = [
            ("valid", rotate_native_refresh, token),
            ("wrong", rotate_native_refresh, wrong_token),
        ]

        with self.workers_blocked_by(
            lambda: User.objects.select_for_update().get(pk=self.user.pk),
            calls,
        ) as run:
            pass

        results = run["results"]
        self.assertEqual(results["valid"].code, "refresh_rotated")
        self.assertEqual(results["wrong"].code, "invalid_refresh")
        session.refresh_from_db()
        predecessor.refresh_from_db()
        self.assertEqual(session.status, AuthSession.Status.ACTIVE)
        self.assertIsNotNone(predecessor.replaced_by_id)
        self.assertEqual(RefreshCredential.objects.filter(session=session).count(), 2)
        self.assertEqual(
            RefreshCredential.objects.filter(
                session=session,
                used_at__isnull=True,
                revoked_at__isnull=True,
            ).count(),
            1,
        )

    def test_refresh_waiting_for_user_lock_does_not_lock_session_or_credential(self):
        session, credential, token = self.create_refresh(AuthSession.ClientType.NATIVE)

        with self.workers_blocked_by(
            lambda: User.objects.select_for_update().get(pk=self.user.pk),
            [("rotate", rotate_native_refresh, token)],
        ) as run:
            AuthSession.objects.select_for_update(nowait=True).get(pk=session.pk)
            RefreshCredential.objects.select_for_update(nowait=True).get(pk=credential.pk)

        self.assertEqual(run["results"]["rotate"].code, "refresh_rotated")

    def test_refresh_waiting_for_session_lock_does_not_lock_credential(self):
        session, credential, token = self.create_refresh(AuthSession.ClientType.NATIVE)

        with self.workers_blocked_by(
            lambda: AuthSession.objects.select_for_update().get(pk=session.pk),
            [("rotate", rotate_native_refresh, token)],
        ) as run:
            RefreshCredential.objects.select_for_update(nowait=True).get(pk=credential.pk)

        self.assertEqual(run["results"]["rotate"].code, "refresh_rotated")

    def test_refresh_locks_only_presented_and_related_credentials(self):
        session, credential, token = self.create_refresh(AuthSession.ClientType.NATIVE)
        historical = RefreshCredential.objects.create(
            uuid=uuid.UUID(int=0),
            session=session,
            secret_digest=refresh_secret_digest(
                uuid.UUID(int=0),
                b"h" * 32,
                self.key_material.refresh_hmac_key,
            ),
            expires_at=self.now + timedelta(days=7),
            used_at=self.now,
            revoked_at=self.now,
        )

        with self.workers_blocked_by(
            lambda: RefreshCredential.objects.select_for_update().get(pk=credential.pk),
            [("rotate", rotate_native_refresh, token)],
        ) as run:
            RefreshCredential.objects.select_for_update(nowait=True).get(pk=historical.pk)

        self.assertEqual(run["results"]["rotate"].code, "refresh_rotated")
