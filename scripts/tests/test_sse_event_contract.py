import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "check-api-types.py"
SPEC = importlib.util.spec_from_file_location("sse_api_gate", SCRIPT)
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


class TradingEventContractTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.shared = Path(directory.name)
        (self.shared / "constants").mkdir()
        self.source = self.shared / "constants/trading.ts"
        self.declare("'order_created' | 'swap_failed'")
        scoped = patch.object(gate, "SHARED", self.shared)
        scoped.start()
        self.addCleanup(scoped.stop)
        self.stream = {
            "x-sse-events": ["connected", "order_created", "swap_failed"],
            "x-sse-connection-event": "connected",
        }
        self.document = {"paths": {
            "/api/trading/events/": {"get": {"responses": {"200": {
                "content": {"text/event-stream": {"schema": self.stream}}
            }}}}
        }}

    def declare(self, union):
        self.source.write_text(
            "export const TRADING_ENDPOINTS = {\n"
            "  EVENTS: {\n"
            "    STREAM: '/api/trading/events/',\n"
            "  },\n"
            "} as const;\n"
            f"export type TradingEventType = {union};\n"
        )

    def test_matching_events_need_no_invalidation_for_the_connection(self):
        self.assertEqual(gate.trading_event_drift(self.document), [])

    def test_a_server_event_rename_reports_both_halves_of_the_drift(self):
        self.stream["x-sse-events"][1] = "order_submitted"
        self.assertEqual(gate.trading_event_drift(self.document), [
            "No client invalidation for server events: order_submitted",
            "Client listens for events the server never sends: order_created",
        ])

    def test_a_new_server_event_needs_a_client_listener(self):
        self.stream["x-sse-events"].append("order_expired")
        self.assertEqual(gate.trading_event_drift(self.document), [
            "No client invalidation for server events: order_expired",
        ])

    def test_a_client_listener_needs_a_server_event(self):
        self.declare("'order_created' | 'swap_failed' | 'order_expired'")
        self.assertEqual(gate.trading_event_drift(self.document), [
            "Client listens for events the server never sends: order_expired",
        ])

    def test_the_connection_event_comes_from_the_schema(self):
        self.stream["x-sse-events"][0] = "ready"
        self.stream["x-sse-connection-event"] = "ready"
        self.assertEqual(gate.trading_event_drift(self.document), [])

    def test_connection_metadata_cannot_be_omitted(self):
        del self.stream["x-sse-connection-event"]
        with self.assertRaisesRegex(gate.Unresolvable, "declare its events and connection event"):
            gate.trading_event_drift(self.document)

    def test_an_empty_malformed_or_repeated_event_list_is_not_a_clean_contract(self):
        for events in ([], "connected", [None], ["connected", "connected"]):
            with self.subTest(events=events):
                self.stream["x-sse-events"] = events
                with self.assertRaisesRegex(gate.Unresolvable, "unique strings"):
                    gate.trading_event_drift(self.document)

    def test_a_different_stream_path_cannot_satisfy_the_client_endpoint(self):
        self.document["paths"]["/some-other-stream/"] = self.document["paths"].pop("/api/trading/events/")
        with self.assertRaisesRegex(gate.Unresolvable, "declare its events"):
            gate.trading_event_drift(self.document)

    def test_an_uninspectable_union_is_refused(self):
        for union in ("string", "OtherEvents", "'order_created' | string"):
            with self.subTest(union=union):
                self.declare(union)
                with self.assertRaisesRegex(gate.Unresolvable, "inspectable string-literal union"):
                    gate.trading_event_drift(self.document)

    def test_comments_and_string_values_do_not_declare_another_union(self):
        self.declare("| 'order_created' /* stable */ | \"swap_failed\"")
        with self.source.open("a") as source:
            source.write("// export type TradingEventType = 'wrong';\n")
            source.write("const label = \"export type TradingEventType = 'also_wrong';\";\n")
        self.assertEqual(gate.trading_event_drift(self.document), [])

    def test_a_missing_or_duplicate_union_cannot_be_reported_as_checked(self):
        original = self.source.read_text()
        for text in (
            original.replace("export type TradingEventType", "export type RenamedType"),
            original + "export type TradingEventType = 'duplicate';\n",
        ):
            with self.subTest(text=text):
                self.source.write_text(text)
                with self.assertRaisesRegex(gate.Unresolvable, "exactly one"):
                    gate.trading_event_drift(self.document)
