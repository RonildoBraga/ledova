#!/usr/bin/env python3
"""Prove the schema response gate reads what a view returns, not what it declares."""

from __future__ import annotations

import ast
import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "check-schema-responses.py"
_spec = importlib.util.spec_from_file_location("check_schema_responses", SCRIPT)
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)


def method(source: str) -> ast.FunctionDef:
    return next(n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.FunctionDef))


class AHandBuiltSerializerIsAFinding(unittest.TestCase):

    def test_a_serializer_built_inside_response_is_found(self):
        node = method("def create(self, request):\n    return Response(DetailSerializer(x).data)\n")

        self.assertEqual(gate.serializers_returned(node), {"DetailSerializer"})

    def test_a_serializer_nested_in_an_envelope_is_found(self):
        node = method(
            "def deploy(self, request):\n"
            "    return Response({'message': 'ok', 'token': DetailSerializer(x).data})\n"
        )

        self.assertEqual(gate.serializers_returned(node), {"DetailSerializer"})

    def test_the_serializer_the_generator_already_infers_is_not_a_finding(self):
        node = method(
            "def create(self, request):\n"
            "    serializer = self.get_serializer(data=request.data)\n"
            "    return Response(serializer.data)\n"
        )

        self.assertEqual(gate.serializers_returned(node), set())

    def test_a_declared_method_is_exempt(self):
        node = method(
            "@extend_schema(responses=DetailSerializer)\n"
            "def create(self, request):\n"
            "    return Response(DetailSerializer(x).data)\n"
        )

        self.assertTrue(gate.declares_schema(node))

    def test_exclude_counts_as_a_declaration(self):
        node = method("@extend_schema(exclude=True)\ndef post(self, request):\n    return Response({'ok': 1})\n")

        self.assertTrue(gate.declares_schema(node))


class ALiteralBodyIsAFinding(unittest.TestCase):

    def test_a_dict_response_is_found(self):
        node = method("def unread_count(self, request):\n    return Response({'unreadCount': n})\n")

        self.assertTrue(gate.builds_a_dict(node))

    def test_an_error_path_is_not_the_contract(self):
        node = method(
            "def token_refresh(self, request):\n"
            "    return Response({'error': 'no token'}, status=status.HTTP_400_BAD_REQUEST)\n"
        )

        self.assertFalse(gate.builds_a_dict(node))

    def test_an_explicit_success_status_is_still_the_contract(self):
        node = method("def sync(self, request):\n    return Response({'ok': 1}, status=status.HTTP_200_OK)\n")

        self.assertTrue(gate.builds_a_dict(node))

    def test_an_empty_body_says_nothing_about_a_shape(self):
        node = method("def destroy(self, request):\n    return Response({})\n")

        self.assertFalse(gate.builds_a_dict(node))


class APrivateHelperIsAttributedToItsCallers(unittest.TestCase):

    def test_the_helper_a_method_calls_is_found(self):
        node = method("def submit(self, request):\n    return self._detail(x)\n")

        self.assertEqual(gate.helpers_called(node), {"_detail"})

    def test_a_public_call_is_not_a_helper(self):
        node = method("def submit(self, request):\n    return self.detail(x)\n")

        self.assertEqual(gate.helpers_called(node), set())


class TheRepositoryStaysClean(unittest.TestCase):

    def test_the_gate_passes_on_this_tree(self):
        findings, checked = gate.scan()
        counts: dict[str, int] = {}
        for finding in findings:
            key = finding.split(" ")[0].rsplit(":", 1)[0] + ":" + finding.rsplit(": ", 1)[1]
            counts[key] = counts.get(key, 0) + 1

        self.assertGreater(checked, 0)
        self.assertEqual(
            {key: count for key, count in counts.items() if count > gate.LEGACY.get(key, 0)},
            {},
        )

    def test_no_legacy_count_is_higher_than_what_is_there(self):
        findings, _checked = gate.scan()
        counts: dict[str, int] = {}
        for finding in findings:
            key = finding.split(" ")[0].rsplit(":", 1)[0] + ":" + finding.rsplit(": ", 1)[1]
            counts[key] = counts.get(key, 0) + 1

        self.assertEqual(
            sorted(key for key, pinned in gate.LEGACY.items() if counts.get(key, 0) < pinned),
            [],
        )

    def test_every_legacy_entry_names_a_rule_the_gate_knows(self):
        for key in gate.LEGACY:
            with self.subTest(key=key):
                self.assertIn(key.rsplit(":", 1)[1], gate.RULES)


if __name__ == "__main__":
    unittest.main()
