import importlib.util
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from io import StringIO
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "check-api-schema.py"
SPEC = importlib.util.spec_from_file_location("check_api_schema", SCRIPT)
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


class SchemaSnapshotTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.generated = self.root / "generated.json"
        self.snapshot = self.root / "snapshot.json"
        self.report = self.root / "report.json"
        self.document = {
            "openapi": "3.0.3",
            "paths": {
                "/api/things/": {
                    "get": {
                        "responses": {
                            "200": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Thing"}}}}
                        }
                    }
                }
            },
            "components": {
                "schemas": {
                    "Thing": {
                        "type": "object",
                        "required": ["amount", "state"],
                        "properties": {
                            "amount": {
                                "type": "integer",
                                "maximum": 9223372036854775807,
                                "minimum": 0,
                            },
                            "state": {"type": "string", "nullable": True},
                            "secret": {"type": "string", "writeOnly": True},
                        },
                        "x-sse-events": ["connected", "changed"],
                    }
                }
            },
        }
        self.generated.write_text(json.dumps(self.document))
        self.snapshot.write_text(json.dumps(self.document))

    def invoke(self, *extra):
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            return gate.main(
                [
                    "--schema",
                    str(self.generated),
                    "--snapshot",
                    str(self.snapshot),
                    "--report",
                    str(self.report),
                    *extra,
                ]
            )

    def test_mapping_order_is_the_only_ignored_difference(self):
        self.snapshot.write_text(json.dumps(self.document, sort_keys=True, indent=4))
        self.assertEqual(self.invoke(), 0)

    def test_field_bounds_nullability_write_only_media_and_event_changes_fail_without_rewriting(
        self,
    ):
        original = self.snapshot.read_bytes()
        changes = [
            ("components", "schemas", "Thing", "properties", "amount", "maximum"),
            ("components", "schemas", "Thing", "properties", "amount", "minimum"),
            ("components", "schemas", "Thing", "properties", "state", "nullable"),
            ("components", "schemas", "Thing", "properties", "secret", "writeOnly"),
            ("components", "schemas", "Thing", "required"),
            ("components", "schemas", "Thing", "x-sse-events"),
            ("paths", "/api/things/", "get", "responses", "200", "content"),
        ]
        for trail in changes:
            with self.subTest(trail=trail):
                changed = deepcopy(self.document)
                target = changed
                for key in trail[:-1]:
                    target = target[key]
                del target[trail[-1]]
                self.generated.write_text(json.dumps(changed))
                self.assertEqual(self.invoke(), 1)
                self.assertEqual(self.snapshot.read_bytes(), original)
                self.assertFalse(json.loads(self.report.read_text())["matches"])

    def test_array_order_is_preserved(self):
        self.document["components"]["schemas"]["Thing"]["required"].reverse()
        self.generated.write_text(json.dumps(self.document))
        self.assertEqual(self.invoke(), 1)

    def test_a_missing_snapshot_fails_without_creating_one(self):
        self.snapshot.unlink()
        self.assertEqual(self.invoke(), 1)
        self.assertFalse(self.snapshot.exists())

    def test_only_an_explicit_update_writes_the_complete_canonical_document(self):
        self.snapshot.unlink()
        self.assertEqual(self.invoke("--update"), 0)
        self.assertEqual(json.loads(self.snapshot.read_text()), self.document)
        self.assertEqual(self.snapshot.read_text(), gate.canonical_document(self.generated))
        self.assertEqual(self.invoke(), 0)

    def test_duplicate_keys_and_nonfinite_values_are_not_silently_normalized(self):
        original = self.snapshot.read_bytes()
        for content in (
            '{"openapi":"3.0.3","paths":{},"paths":{}}',
            '{"openapi":"3.0.3","paths":{},"value":NaN}',
        ):
            with self.subTest(content=content):
                self.generated.write_text(content)
                self.assertEqual(self.invoke("--update"), 1)
                self.assertEqual(self.snapshot.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
