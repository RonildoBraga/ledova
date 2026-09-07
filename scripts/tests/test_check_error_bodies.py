#!/usr/bin/env python3
"""Prove the error body gate sees an exception's text however it is spelled."""

from __future__ import annotations

import ast
import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "check-error-bodies.py"
_spec = importlib.util.spec_from_file_location("check_error_bodies", SCRIPT)
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)

SUBCLASSES = {"TransferPreparationException", "BlockchainAPIError"}


def findings(source: str):
    tree = ast.parse(source)
    return gate.findings_in(tree, SUBCLASSES, Path("service.py"))


class AnExceptionsTextReachingTheBody(unittest.TestCase):

    def test_the_bare_name(self):
        self.assertEqual(
            len(findings("try:\n    x()\nexcept Exception as e:\n    raise TransferPreparationException(e)\n")), 1
        )

    def test_str_of_it(self):
        self.assertEqual(
            len(findings("try:\n    x()\nexcept Exception as e:\n    raise TransferPreparationException(str(e))\n")), 1
        )

    def test_an_f_string_interpolating_it(self):
        self.assertEqual(
            len(findings(
                'try:\n    x()\nexcept Exception as e:\n    raise TransferPreparationException(f"failed: {e}")\n'
            )), 1
        )

    def test_a_local_it_was_assigned_to(self):
        self.assertEqual(
            len(findings(
                "try:\n    x()\nexcept Exception as e:\n"
                '    raw = str(e)\n    raise TransferPreparationException(f"failed: {raw}")\n'
            )), 1
        )

    def test_a_keyword_argument(self):
        self.assertEqual(
            len(findings(
                "try:\n    x()\nexcept Exception as e:\n    raise TransferPreparationException(detail=str(e))\n"
            )), 1
        )


class WhatIsNotAFinding(unittest.TestCase):

    def test_a_fixed_message(self):
        self.assertEqual(
            findings(
                'try:\n    x()\nexcept Exception as e:\n    raise TransferPreparationException("It failed.") from e\n'
            ), []
        )

    def test_logging_the_diagnostic(self):
        self.assertEqual(
            findings(
                "try:\n    x()\nexcept Exception as e:\n"
                '    logger.error(f"failed: {e}")\n    raise TransferPreparationException("It failed.") from e\n'
            ), []
        )

    def test_a_message_built_from_the_repositorys_own_state(self):
        self.assertEqual(
            findings(
                "try:\n    x()\nexcept Exception as e:\n"
                '    raise TransferPreparationException(f"status {order.get_status_display()}") from e\n'
            ), []
        )

    def test_a_sanitiser(self):
        self.assertEqual(
            findings(
                "try:\n    x()\nexcept Exception as e:\n"
                "    friendly = decode_exception_to_message(e, 'Failed')\n"
                '    raise TransferPreparationException(f"failed: {friendly}") from e\n'
            ), []
        )

    def test_a_non_api_exception(self):
        self.assertEqual(
            findings('try:\n    x()\nexcept Exception as e:\n    raise ValueError(str(e))\n'), []
        )

    def test_an_unnamed_handler_has_nothing_to_leak(self):
        self.assertEqual(
            findings('try:\n    x()\nexcept Exception:\n    raise TransferPreparationException("It failed.")\n'), []
        )


class TheSubclassSetComesFromTheSource(unittest.TestCase):

    def test_it_follows_apiexception_through_subclassing(self):
        names = gate.api_exception_names()

        self.assertIn("TransferPreparationException", names)
        self.assertIn("BlockchainAPIError", names)

    def test_it_is_large_enough_to_be_real(self):
        self.assertGreater(len(gate.api_exception_names()), 50)


class TheRepositoryStaysClean(unittest.TestCase):

    def test_no_new_finding(self):
        found, checked = gate.scan()
        counts: dict[str, int] = {}
        for finding in found:
            counts[finding.split(":")[0]] = counts.get(finding.split(":")[0], 0) + 1

        self.assertGreater(checked, 0)
        self.assertEqual({k: v for k, v in counts.items() if v > gate.LEGACY.get(k, 0)}, {})

    def test_no_pinned_count_is_stale(self):
        found, _checked = gate.scan()
        counts: dict[str, int] = {}
        for finding in found:
            counts[finding.split(":")[0]] = counts.get(finding.split(":")[0], 0) + 1

        self.assertEqual(sorted(k for k, v in gate.LEGACY.items() if counts.get(k, 0) < v), [])


if __name__ == "__main__":
    unittest.main()
