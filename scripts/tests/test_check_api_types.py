#!/usr/bin/env python3
"""Prove the API type drift gate matches through paths, and not through names.

The name-collision case has its own test because a name-matching version of this
gate reported a bug that did not exist (#207, closed as invalid): it compared a
"DocumentUpload" component generated from documents.DocumentUploadSerializer
against a "DocumentUpload" interface describing the companies upload endpoint.
Two apps, two models, two endpoints, one word in common.
"""

from __future__ import annotations

import importlib.util
import tempfile
import textwrap
import unittest
from pathlib import Path

import yaml

SCRIPT = Path(__file__).resolve().parent.parent / "check-api-types.py"
_spec = importlib.util.spec_from_file_location("check_api_types", SCRIPT)
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)


class _Repository(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.root = Path(self._directory.name)
        self.shared = self.root / "packages/shared/src"
        (self.shared / "constants").mkdir(parents=True)
        (self.shared / "services").mkdir()
        (self.shared / "types").mkdir()
        gate.ROOT = self.root
        gate.SHARED = self.shared

    def endpoints(self, body: str):
        (self.shared / "constants/api.ts").write_text(
            f"export const ENDPOINTS = {{\n{textwrap.dedent(body)}\n}}\n"
        )

    def service(self, body: str):
        (self.shared / "services/thing.ts").write_text(textwrap.dedent(body))

    def types(self, body: str):
        (self.shared / "types/thing.ts").write_text(textwrap.dedent(body))

    def schema(self, document: dict) -> Path:
        path = self.root / "schema.yml"
        path.write_text(yaml.safe_dump(document))
        return path

    def findings(self, document: dict):
        findings, _matched = gate.scan(self.schema(document))
        return [(name, component, absent) for _endpoint, name, component, absent in findings]


def operation(verb: str, path: str, component: str) -> dict:
    return {
        path: {
            verb: {
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": f"#/components/schemas/{component}"}
                            }
                        }
                    }
                }
            }
        }
    }


class MatchingGoesThroughPaths(_Repository):

    def test_a_shared_name_on_a_different_endpoint_is_not_compared(self):
        """The #207 case: same component name, unrelated endpoint."""
        self.endpoints("  THING: (uuid: string) => `/api/companies/${uuid}/documents/` as const,")
        self.service("export const upload = (c) => c.post<DocumentUpload>(ENDPOINTS.THING(u), d);")
        self.types("export interface DocumentUpload {\n  name: string;\n  file: File;\n}\n")

        document = {
            "paths": operation("post", "/api/companies/{uuid}/documents/", "CompanyDocument"),
            "components": {
                "schemas": {
                    "CompanyDocument": {"properties": {"name": {}, "file": {}}},
                    "DocumentUpload": {"properties": {"note": {}, "file": {}}},
                }
            },
        }

        self.assertEqual(self.findings(document), [])

    def test_a_field_the_endpoints_own_component_omits_is_reported(self):
        self.endpoints("  THING: '/api/things/' as const,")
        self.service("export const get = (c) => c.get<Thing>(ENDPOINTS.THING);")
        self.types("export interface Thing {\n  uuid: string;\n  createdAt: string;\n}\n")

        document = {
            "paths": operation("get", "/api/things/", "Thing"),
            "components": {"schemas": {"Thing": {"properties": {"uuid": {}}}}},
        }

        self.assertEqual(self.findings(document), [("Thing", "Thing", ["createdat"])])

    def test_a_verb_that_does_not_match_is_not_compared(self):
        self.endpoints("  THING: '/api/things/' as const,")
        self.service("export const post = (c) => c.post<Thing>(ENDPOINTS.THING, d);")
        self.types("export interface Thing {\n  uuid: string;\n}\n")

        document = {
            "paths": operation("get", "/api/things/", "Thing"),
            "components": {"schemas": {"Thing": {"properties": {}}}},
        }

        self.assertEqual(self.findings(document), [])

    def test_a_path_parameter_matches_whatever_it_is_named(self):
        self.endpoints("  THING: (id: string) => `/api/things/${id}/` as const,")
        self.service("export const get = (c) => c.get<Thing>(ENDPOINTS.THING(i));")
        self.types("export interface Thing {\n  missing: string;\n}\n")

        document = {
            "paths": operation("get", "/api/things/{thing_uuid}/", "Thing"),
            "components": {"schemas": {"Thing": {"properties": {"other": {}}}}},
        }

        self.assertEqual(self.findings(document), [("Thing", "Thing", ["missing"])])


class OnlyTheDirectionThatBreaksAtRuntime(_Repository):
    def setUp(self):
        super().setUp()
        self.endpoints("  THING: '/api/things/' as const,")
        self.service("export const get = (c) => c.get<Thing>(ENDPOINTS.THING);")

    def document(self, properties: dict) -> dict:
        return {
            "paths": operation("get", "/api/things/", "Thing"),
            "components": {"schemas": {"Thing": {"properties": properties}}},
        }

    def test_an_optional_field_the_api_omits_is_not_reported(self):
        self.types("export interface Thing {\n  uuid: string;\n  extra?: string;\n}\n")

        self.assertEqual(self.findings(self.document({"uuid": {}})), [])

    def test_a_field_the_api_sends_that_no_type_models_is_not_reported(self):
        self.types("export interface Thing {\n  uuid: string;\n}\n")

        self.assertEqual(self.findings(self.document({"uuid": {}, "unmodelled": {}})), [])

    def test_a_write_only_field_is_not_expected_in_a_response(self):
        self.types("export interface Thing {\n  uuid: string;\n}\n")

        self.assertEqual(self.findings(self.document({"uuid": {}, "secret": {"writeOnly": True}})), [])

    def test_separators_and_case_do_not_make_one_field_read_as_two(self):
        self.types("export interface Thing {\n  addressLine1: string;\n}\n")

        self.assertEqual(self.findings(self.document({"address_line_1": {}})), [])


class InheritedFieldsAreCounted(_Repository):

    def test_a_field_from_an_extended_interface_is_required_too(self):
        self.endpoints("  THING: '/api/things/' as const,")
        self.service("export const get = (c) => c.get<Thing>(ENDPOINTS.THING);")
        self.types(
            "export interface Base {\n  uuid: string;\n  updatedAt: string;\n}\n"
            "export interface Thing extends Base {\n  name: string;\n}\n"
        )

        document = {
            "paths": operation("get", "/api/things/", "Thing"),
            "components": {"schemas": {"Thing": {"properties": {"uuid": {}, "name": {}}}}},
        }

        self.assertEqual(self.findings(document), [("Thing", "Thing", ["updatedat"])])

    def test_only_the_picked_fields_of_a_pick_are_required(self):
        self.endpoints("  THING: '/api/things/' as const,")
        self.service("export const get = (c) => c.get<Thing>(ENDPOINTS.THING);")
        self.types(
            "export interface Base {\n  uuid: string;\n  updatedAt: string;\n}\n"
            "export interface Thing extends Pick<Base, 'uuid'> {\n  name: string;\n}\n"
        )

        document = {
            "paths": operation("get", "/api/things/", "Thing"),
            "components": {"schemas": {"Thing": {"properties": {"uuid": {}, "name": {}}}}},
        }

        self.assertEqual(self.findings(document), [])


class TheTwoListsStaySeparate(unittest.TestCase):

    def test_no_key_is_carried_by_both_lists(self):
        self.assertEqual(set(gate.TYPE_DEBT) & set(gate.SCHEMA_DEBT), set())

    def test_every_pinned_entry_states_a_reason(self):
        for key, (_count, reason) in {**gate.TYPE_DEBT, **gate.SCHEMA_DEBT}.items():
            with self.subTest(key=key):
                self.assertGreater(len(reason), 60, f"{key} needs a reason, not a label")

    def test_every_schema_debt_entry_names_the_issue_that_empties_it(self):
        for key, (_count, reason) in gate.SCHEMA_DEBT.items():
            with self.subTest(key=key):
                self.assertIn("#211", reason)


if __name__ == "__main__":
    unittest.main()
