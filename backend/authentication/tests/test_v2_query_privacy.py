from unittest.mock import patch

from django.db import connection, connections
from django.test import SimpleTestCase, override_settings

from authentication.services.v2_query_privacy import _require_unrecorded_v2_connection


class ConnectionMap:
    def __init__(self, values):
        self.values = values
        self.accessed = []

    def __getitem__(self, alias):
        self.accessed.append(alias)
        value = self.values[alias]
        if isinstance(value, Exception):
            raise value
        return value


class QueryStateConnection:
    def __init__(self, queries_logged):
        self.queries_logged = queries_logged


class FailingQueryStateConnection:
    def __init__(self, exception):
        self.exception = exception

    @property
    def queries_logged(self):
        raise self.exception


@override_settings(DEBUG=False)
class V2QueryPrivacyTest(SimpleTestCase):
    error = "V2 challenge service unavailable."

    def assert_fixed_rejection(self, action, sensitive_value=None):
        with self.assertRaises(RuntimeError) as raised:
            action()

        exception = raised.exception
        self.assertEqual(str(exception), self.error)
        self.assertEqual(repr(exception), f"RuntimeError({self.error!r})")
        self.assertEqual(exception.args, (self.error,))
        self.assertIsNone(exception.__cause__)
        self.assertIsNone(exception.__context__)
        if sensitive_value is not None:
            rendered = f"{exception!s} {exception!r} {exception.args!r}"
            self.assertNotIn(sensitive_value, rendered)

    def test_returns_the_selected_connection_when_query_recording_is_disabled(self):
        with patch.object(connection, "force_debug_cursor", False):
            selected = _require_unrecorded_v2_connection(using="default")

        self.assertIs(selected, connections["default"])

    @override_settings(DEBUG=True)
    def test_rejects_debug_query_recording(self):
        with patch.object(connection, "force_debug_cursor", False):
            self.assert_fixed_rejection(lambda: _require_unrecorded_v2_connection(using="default"))

    def test_rechecks_and_rejects_forced_debug_cursor_recording(self):
        with patch.object(connection, "force_debug_cursor", False):
            selected = _require_unrecorded_v2_connection(using="default")

        with patch.object(connection, "force_debug_cursor", True):
            self.assert_fixed_rejection(lambda: _require_unrecorded_v2_connection(using="default"))

        self.assertIs(selected, connections["default"])

    def test_checks_and_returns_only_the_requested_connection(self):
        selected = QueryStateConnection(False)
        connection_map = ConnectionMap(
            {
                "challenge": selected,
                "default": AssertionError("unselected connection accessed"),
            }
        )

        with patch("authentication.services.v2_query_privacy.connections", connection_map):
            result = _require_unrecorded_v2_connection(using="challenge")

        self.assertIs(result, selected)
        self.assertEqual(connection_map.accessed, ["challenge"])

    def test_connection_lookup_failure_is_redacted_without_exception_chaining(self):
        sensitive_value = "private-connection-alias-marker"
        connection_map = ConnectionMap({"challenge": ValueError(sensitive_value)})

        with patch("authentication.services.v2_query_privacy.connections", connection_map):
            self.assert_fixed_rejection(
                lambda: _require_unrecorded_v2_connection(using="challenge"),
                sensitive_value,
            )

    def test_query_state_failure_is_redacted_without_exception_chaining(self):
        sensitive_value = "private-query-state-marker"
        connection_map = ConnectionMap({"challenge": FailingQueryStateConnection(ValueError(sensitive_value))})

        with patch("authentication.services.v2_query_privacy.connections", connection_map):
            self.assert_fixed_rejection(
                lambda: _require_unrecorded_v2_connection(using="challenge"),
                sensitive_value,
            )

    def test_rejects_every_non_boolean_false_query_state(self):
        for state in (None, 0, "", object()):
            with self.subTest(state=type(state).__name__):
                connection_map = ConnectionMap({"challenge": QueryStateConnection(state)})
                with patch("authentication.services.v2_query_privacy.connections", connection_map):
                    self.assert_fixed_rejection(lambda: _require_unrecorded_v2_connection(using="challenge"))

    def test_does_not_execute_sql(self):
        with patch.object(connection, "force_debug_cursor", False):
            _require_unrecorded_v2_connection(using="default")
