#!/usr/bin/env python3
"""Prove the shadowing gate refuses a helper that replaces an assertion's raiser."""

from __future__ import annotations

import ast
import importlib.util
import unittest
from decimal import Decimal
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "check-test-shadowing.py"
_spec = importlib.util.spec_from_file_location("check_test_shadowing", SCRIPT)
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)


def names(source: str):
    return {
        f"{class_name}.{method}"
        for _, class_name, method in gate.shadowing(ast.parse(source))
    }


class AHelperThatReplacesAnAssertionIsAFinding(unittest.TestCase):

    def test_a_helper_named_fail_is_found(self):
        source = "class T(TestCase):\n    def fail(self, tx):\n        return tx\n"

        self.assertEqual(names(source), {"T.fail"})

    def test_a_helper_named_after_an_assertion_is_found(self):
        source = "class T(TestCase):\n    def assertEqual(self, a, b):\n        return None\n"

        self.assertEqual(names(source), {"T.assertEqual"})

    def test_an_async_helper_is_found_too(self):
        source = (
            "class T(TestCase):\n    async def fail(self, tx):\n        return tx\n"
        )

        self.assertEqual(names(source), {"T.fail"})

    def test_the_override_hooks_are_not_findings(self):
        source = (
            "class T(TestCase):\n"
            "    def setUp(self):\n        pass\n"
            "    def tearDown(self):\n        pass\n"
            "    @classmethod\n    def setUpClass(cls):\n        pass\n"
            "    @classmethod\n    def setUpTestData(cls):\n        pass\n"
        )

        self.assertEqual(names(source), set())

    def test_an_ordinary_helper_is_not_a_finding(self):
        source = (
            "class T(TestCase):\n    def a_signed_cancel(self):\n        return None\n"
        )

        self.assertEqual(names(source), set())


class TheDefectTheGateIsAbout(unittest.TestCase):

    def test_a_shadowed_fail_makes_a_tuple_assertion_stop_raising(self):
        class Shadowed(unittest.TestCase):
            def fail(self, msg=None):
                return "swallowed"

            def runTest(self):
                pass

        shadowed = Shadowed()

        shadowed.assertEqual((Decimal("1"), Decimal("2")), (Decimal("3"), Decimal("4")))

        with self.assertRaises(AssertionError):
            shadowed.assertTrue(False)

    def test_the_same_assertion_raises_without_the_shadow(self):
        class Ordinary(unittest.TestCase):
            def runTest(self):
                pass

        with self.assertRaises(AssertionError):
            Ordinary().assertEqual(
                (Decimal("1"), Decimal("2")), (Decimal("3"), Decimal("4"))
            )


class TheReservedSetIsDerivedRatherThanListed(unittest.TestCase):

    def test_fail_and_the_assertions_are_reserved(self):
        self.assertIn("fail", gate.RESERVED)
        self.assertIn("assertEqual", gate.RESERVED)
        self.assertIn("assertRaises", gate.RESERVED)

    def test_the_override_hooks_are_not_reserved(self):
        self.assertEqual(gate.RESERVED & gate.OVERRIDABLE, frozenset())
        self.assertIn("setUp", gate.OVERRIDABLE)


if __name__ == "__main__":
    unittest.main()
