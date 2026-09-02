import asyncio
import logging
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from inspect import signature
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase
from procrastinate import App, RetryStrategy
from procrastinate.testing import InMemoryConnector
from procrastinate.worker import Worker

from authentication.tasks import V2_DELIVERY_HOLD_QUEUE, deliver_v2_challenge
from ledova_backend import worker_entrypoint
from ledova_backend.logging_filters import (
    AUDITED_PROCRASTINATE_VERSION,
    V2_DELIVERY_TASK_NAME,
    V2ProcrastinateLogFilter,
)
from ledova_backend.procrastinate_app import app as django_procrastinate_app

_PRIVATE_SUCCESS_UUID = "10000000-0000-4000-8000-000000000001"
_PRIVATE_ERROR_UUID = "10000000-0000-4000-8000-000000000002"
_PRIVATE_SHUTDOWN_UUID = "10000000-0000-4000-8000-000000000003"
_PRIVATE_RESULT = "PRIVATE_RESULT_MARKER"
_PRIVATE_ERROR = "PRIVATE_ERROR_MARKER"
_PUBLIC_CONTROL = "PUBLIC_CONTROL_MARKER"
_VERSION_ERROR = "Unsupported Procrastinate logging contract."


class _TrackingFilter(V2ProcrastinateLogFilter):
    def __init__(self):
        super().__init__()
        self.decisions = []

    def filter(self, record):
        decision = super().filter(record)
        action = record.__dict__.get("action")
        if type(action) is str:
            self.decisions.append((action, decision))
        return decision


class _FormattedLogCapture:
    def __init__(self):
        self.stream = StringIO()
        self.filter = _TrackingFilter()
        self.handler = logging.StreamHandler(self.stream)
        self.handler.setLevel(logging.DEBUG)
        self.handler.setFormatter(logging.Formatter("{levelname} {name} {message}", style="{"))
        self.handler.addFilter(self.filter)
        self.logger = logging.getLogger("procrastinate")
        self.original_handlers = None
        self.original_level = None
        self.original_propagate = None
        self.original_disabled = None

    def __enter__(self):
        self.original_handlers = self.logger.handlers[:]
        self.original_level = self.logger.level
        self.original_propagate = self.logger.propagate
        self.original_disabled = self.logger.disabled
        self.logger.handlers = [self.handler]
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False
        self.logger.disabled = False
        return self

    def __exit__(self, _exc_type, _exc_value, _traceback):
        self.logger.handlers = self.original_handlers
        self.logger.setLevel(self.original_level)
        self.logger.propagate = self.original_propagate
        self.logger.disabled = self.original_disabled
        self.handler.close()

    def assert_dropped(self, testcase, actions):
        dropped = {action for action, decision in self.filter.decisions if not decision}
        testcase.assertTrue(set(actions).issubset(dropped), (set(actions) - dropped, self.filter.decisions))


class V2ProcrastinateLogFilterTest(SimpleTestCase):
    def assert_private_values_absent(self, captured):
        for value in (
            _PRIVATE_SUCCESS_UUID,
            _PRIVATE_ERROR_UUID,
            _PRIVATE_SHUTDOWN_UUID,
            _PRIVATE_RESULT,
            _PRIVATE_ERROR,
        ):
            self.assertNotIn(value, captured)

    def test_dependency_and_runtime_are_exactly_pinned(self):
        self.assertEqual(package_version("procrastinate"), AUDITED_PROCRASTINATE_VERSION)
        requirements = (Path(settings.BASE_DIR) / "requirements.txt").read_text(encoding="utf-8").splitlines()
        expected = f"procrastinate[django]=={AUDITED_PROCRASTINATE_VERSION}"
        self.assertEqual([line for line in requirements if line.startswith("procrastinate")], [expected])

    def test_registered_v2_task_is_fixed_fail_and_held_out_of_normal_workers(self):
        registered = django_procrastinate_app.tasks[V2_DELIVERY_TASK_NAME]
        self.assertIs(registered, deliver_v2_challenge)
        self.assertEqual(registered.name, V2_DELIVERY_TASK_NAME)
        self.assertEqual(registered.queue, V2_DELIVERY_HOLD_QUEUE)
        self.assertIsNone(registered.retry_strategy)
        self.assertIsNone(registered.lock)
        self.assertIsNone(registered.queueing_lock)
        self.assertEqual(tuple(signature(registered.func).parameters), ("delivery_uuid",))
        parameter = signature(registered.func).parameters["delivery_uuid"]
        self.assertEqual(parameter.kind, parameter.KEYWORD_ONLY)

        with self.assertRaises(RuntimeError) as raised:
            registered.func(delivery_uuid=_PRIVATE_ERROR_UUID)

        self.assertEqual(str(raised.exception), "V2 challenge delivery worker unavailable.")
        self.assertIsNone(raised.exception.__cause__)
        self.assertIsNone(raised.exception.__context__)
        self.assertNotIn(_PRIVATE_ERROR_UUID, f"{raised.exception!s} {raised.exception!r}")

    def test_normal_worker_entrypoints_exclude_the_v2_hold_queue(self):
        backend = Path(settings.BASE_DIR)
        compose = (backend.parent / "docker-compose.yml").read_text(encoding="utf-8")
        makefile = (backend / "Makefile").read_text(encoding="utf-8")
        entrypoint = (backend / "ledova_backend" / "worker_entrypoint.py").read_text(encoding="utf-8")
        command = "python manage.py procrastinate worker --queues=default,builtin"

        self.assertIn(f"command: {command}", compose)
        self.assertIn("exec $(PYTHON) manage.py procrastinate worker --queues=default,builtin", makefile)
        self.assertIn('"procrastinate", "worker", "--queues=default,builtin"', entrypoint)
        self.assertNotIn("v2_challenge_hold", compose)
        self.assertNotIn("v2_challenge_hold", makefile)
        self.assertNotIn("v2_challenge_hold", entrypoint)

        queues = {name: task.queue for name, task in django_procrastinate_app.tasks.items()}
        self.assertEqual(queues[V2_DELIVERY_TASK_NAME], V2_DELIVERY_HOLD_QUEUE)
        self.assertEqual(
            {queue for name, queue in queues.items() if name != V2_DELIVERY_TASK_NAME},
            {"default", "builtin"},
        )

        with (
            patch.object(worker_entrypoint.threading, "Thread") as thread,
            patch.object(
                worker_entrypoint.subprocess,
                "run",
                return_value=SimpleNamespace(returncode=7),
            ) as run,
            patch.dict(worker_entrypoint.os.environ, {"PORT": "8080"}),
        ):
            self.assertEqual(worker_entrypoint.main(), 7)

        thread.return_value.start.assert_called_once_with()
        run.assert_called_once_with(
            [
                worker_entrypoint.sys.executable,
                "manage.py",
                "procrastinate",
                "worker",
                "--queues=default,builtin",
            ],
            check=False,
        )

    def test_normal_queue_selection_never_executes_the_v2_hold_task(self):
        connector = InMemoryConnector()
        app = App(connector=connector)
        executed = []

        @app.task(name=V2_DELIVERY_TASK_NAME, queue=V2_DELIVERY_HOLD_QUEUE)
        def held(delivery_uuid):
            executed.append(delivery_uuid)

        @app.task(name="tests.normal_queue_control")
        def normal():
            executed.append(_PUBLIC_CONTROL)

        with _FormattedLogCapture() as capture:
            held.defer(delivery_uuid=_PRIVATE_SUCCESS_UUID)
            normal.defer()
            app.run_worker(
                queues=["default", "builtin"],
                wait=False,
                listen_notify=False,
                install_signal_handlers=False,
            )

        jobs = {job["task_name"]: job for job in connector.jobs.values()}
        self.assertEqual(executed, [_PUBLIC_CONTROL])
        self.assertEqual(jobs[V2_DELIVERY_TASK_NAME]["status"], "todo")
        self.assertEqual(jobs["tests.normal_queue_control"]["status"], "succeeded")
        self.assert_private_values_absent(capture.stream.getvalue())

    def test_filter_refuses_unsupported_or_missing_package_version(self):
        for outcome in ("3.9.1", PackageNotFoundError("procrastinate")):
            with self.subTest(outcome=type(outcome).__name__):
                effect = {"return_value": outcome} if isinstance(outcome, str) else {"side_effect": outcome}
                with patch("ledova_backend.logging_filters.package_version", **effect):
                    with self.assertRaisesRegex(RuntimeError, rf"^{_VERSION_ERROR}$") as raised:
                        V2ProcrastinateLogFilter()
                self.assertIsNone(raised.exception.__cause__)

    def test_logging_configuration_is_filtered_non_propagating_and_warning_only(self):
        logger_config = settings.LOGGING["loggers"]["procrastinate"]
        self.assertEqual(logger_config["level"], "WARNING")
        self.assertFalse(logger_config["propagate"])
        self.assertEqual(logger_config["handlers"], ["procrastinate_console"])

        handler_config = settings.LOGGING["handlers"]["procrastinate_console"]
        self.assertEqual(handler_config["level"], "WARNING")
        self.assertEqual(handler_config["filters"], ["v2_procrastinate_privacy"])

        logger = logging.getLogger("procrastinate")
        self.assertEqual(logger.getEffectiveLevel(), logging.WARNING)
        self.assertFalse(logger.propagate)
        self.assertEqual(len(logger.handlers), 1)
        self.assertTrue(any(isinstance(item, V2ProcrastinateLogFilter) for item in logger.handlers[0].filters))

    def test_malformed_structured_extras_fail_closed(self):
        filter_ = V2ProcrastinateLogFilter()
        malformed_job = logging.LogRecord("procrastinate.worker", logging.ERROR, __file__, 1, "private", (), None)
        malformed_job.job = {"args": {"delivery_uuid": _PRIVATE_ERROR_UUID}}
        self.assertFalse(filter_.filter(malformed_job))

        malformed_jobs = logging.LogRecord("procrastinate.jobs", logging.ERROR, __file__, 1, "private", (), None)
        malformed_jobs.jobs = [{"task_name": "other.task"}, object()]
        self.assertFalse(filter_.filter(malformed_jobs))

        other_task = logging.LogRecord("procrastinate.worker", logging.ERROR, __file__, 1, "public", (), None)
        other_task.job = {"task_name": "other.task"}
        self.assertTrue(filter_.filter(other_task))

        other_logger = logging.LogRecord("ledova_backend", logging.ERROR, __file__, 1, "public", (), None)
        other_logger.action = "ending_job"
        self.assertTrue(filter_.filter(other_logger))

    def test_real_defer_start_success_and_non_v2_control(self):
        connector = InMemoryConnector()
        with _FormattedLogCapture() as capture:
            app = App(connector=connector)

            @app.task(name=V2_DELIVERY_TASK_NAME)
            def private_success(delivery_uuid):
                return f"{_PRIVATE_RESULT}:{delivery_uuid}"

            @app.task(name="tests.public_control_task")
            def public_control(marker):
                return marker

            private_success.defer(delivery_uuid=_PRIVATE_SUCCESS_UUID)
            public_control.defer(marker=_PUBLIC_CONTROL)
            app.run_worker(wait=False, listen_notify=False, install_signal_handlers=False)

        captured = capture.stream.getvalue()
        self.assert_private_values_absent(captured)
        self.assertIn(_PUBLIC_CONTROL, captured)
        self.assertEqual({job["status"] for job in connector.jobs.values()}, {"succeeded"})
        capture.assert_dropped(
            self,
            {
                "about_to_defer_jobs",
                "jobs_deferred",
                "loaded_job_info",
                "start_job",
                "job_success",
                "finish_task",
            },
        )

    def test_real_retry_and_terminal_error_are_dropped_before_formatting(self):
        connector = InMemoryConnector()
        with _FormattedLogCapture() as capture:
            app = App(connector=connector)

            @app.task(name=V2_DELIVERY_TASK_NAME, retry=RetryStrategy(max_attempts=1, wait=0))
            def private_failure(delivery_uuid):
                raise RuntimeError(f"{_PRIVATE_ERROR}:{delivery_uuid}")

            private_failure.defer(delivery_uuid=_PRIVATE_ERROR_UUID)
            app.run_worker(wait=False, listen_notify=False, install_signal_handlers=False)

        captured = capture.stream.getvalue()
        self.assert_private_values_absent(captured)
        self.assertEqual(len(connector.jobs), 1)
        job = next(iter(connector.jobs.values()))
        self.assertEqual(job["status"], "failed")
        self.assertEqual(job["attempts"], 2)
        capture.assert_dropped(self, {"job_error_retry", "job_error"})

    def test_real_graceful_shutdown_without_job_extras_is_dropped(self):
        with _FormattedLogCapture() as capture:

            async def exercise_shutdown():
                connector = InMemoryConnector()
                app = App(connector=connector)
                started = asyncio.Event()
                release = asyncio.Event()

                @app.task(name=V2_DELIVERY_TASK_NAME)
                async def private_wait(delivery_uuid):
                    started.set()
                    await release.wait()
                    return delivery_uuid

                await private_wait.defer_async(delivery_uuid=_PRIVATE_SHUTDOWN_UUID)
                worker = Worker(
                    app=app,
                    wait=True,
                    listen_notify=False,
                    install_signal_handlers=False,
                    fetch_job_polling_interval=0.01,
                    abort_job_polling_interval=0.01,
                    shutdown_graceful_timeout=1,
                )
                async with app.open_async():
                    running = asyncio.create_task(worker.run())
                    try:
                        await asyncio.wait_for(started.wait(), timeout=2)
                        worker.stop()

                        async def wait_for_ending_job():
                            while not any(action == "ending_job" for action, _decision in capture.filter.decisions):
                                await asyncio.sleep(0)

                        await asyncio.wait_for(wait_for_ending_job(), timeout=2)
                        release.set()
                        await asyncio.wait_for(running, timeout=2)
                    finally:
                        release.set()
                        if not running.done():
                            worker.stop()
                            running.cancel()
                            await asyncio.gather(running, return_exceptions=True)

            asyncio.run(exercise_shutdown())

        captured = capture.stream.getvalue()
        self.assert_private_values_absent(captured)
        capture.assert_dropped(self, {"ending_job"})
