#!/usr/bin/env python3
"""Prove the connection-binding gate fires, and on the right things.

A gate that reports zero because its pattern stopped matching looks exactly like a gate
that reports zero because the code is clean. Every test here plants something.
"""

from __future__ import annotations

import ast
import importlib.util
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check-connection-binding.py"
_spec = importlib.util.spec_from_file_location("check_connection_binding", SCRIPT)
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)


def findings(source: str) -> list[str]:
    return [called for _, called in gate.findings_for(ast.parse(source))]


class TheGateSeesEachBinding(unittest.TestCase):

    def test_a_bare_atomic_decorator_is_a_finding(self):
        self.assertEqual(findings("@transaction.atomic\ndef f():\n    pass\n"), ["transaction.atomic"])

    def test_a_bare_atomic_context_manager_is_a_finding(self):
        self.assertEqual(findings("with transaction.atomic():\n    pass\n"), ["transaction.atomic"])

    def test_a_bare_atomic_naming_an_alias_is_still_a_finding(self):
        self.assertEqual(findings("with transaction.atomic(using='app'):\n    pass\n"), ["transaction.atomic"])

    def test_on_commit_is_a_finding_because_it_binds_the_same_way(self):
        self.assertEqual(findings("transaction.on_commit(send)\n"), ["transaction.on_commit"])

    def test_a_bare_cursor_is_a_finding_because_the_default_connection_bypasses(self):
        self.assertEqual(findings("with connection.cursor() as c:\n    pass\n"), ["connection.cursor"])

    def test_the_helper_is_not_a_finding(self):
        self.assertEqual(findings("with atomic():\n    pass\n"), [])

    def test_an_aliased_connection_is_not_a_finding(self):
        self.assertEqual(findings("with connections[current_alias()].cursor() as c:\n    pass\n"), [])


class TheRepositoryStaysClean(unittest.TestCase):

    def test_the_gate_reads_a_real_number_of_files_so_a_pass_means_something(self):
        self.assertGreater(len(gate.files()), 400)

    def test_every_allowed_file_exists_and_states_why(self):
        for name, reason in gate.ALLOWED.items():
            with self.subTest(file=name):
                self.assertTrue((REPO_ROOT / name).is_file(), f"{name} is allowed and is not there")
                self.assertGreater(len(reason), 30)

    def test_each_allowed_file_would_otherwise_be_a_finding(self):
        for name in gate.ALLOWED:
            with self.subTest(file=name):
                self.assertTrue(
                    findings((REPO_ROOT / name).read_text()),
                    f"{name} is on the allowlist and breaks no rule, so the entry is stale",
                )


if __name__ == "__main__":
    unittest.main()
