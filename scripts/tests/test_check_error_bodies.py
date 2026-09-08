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


NOTE_METHODS = {"mark_failed", "mark_refused"}


def findings(source: str, notes=frozenset()):
    tree = ast.parse(source)
    return gate.findings_in(tree, SUBCLASSES, set(notes), Path("service.py"))


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


class AnExceptionsTextReachingAFieldAClientReads(unittest.TestCase):

    def test_a_note_method_called_with_it_inside_the_handler(self):
        found = findings(
            "try:\n    x()\nexcept Exception as e:\n    request.mark_failed(str(e))\n", NOTE_METHODS
        )

        self.assertEqual(len(found), 1)
        self.assertIn(gate.SERVES_EXCEPTION_TEXT_TO_A_FIELD, found[0])

    def test_a_note_method_called_after_the_handler_with_a_name_that_outlived_it(self):
        source = (
            "def run():\n"
            "    failure = None\n"
            "    try:\n"
            "        x()\n"
            "    except Exception as e:\n"
            "        failure = e\n"
            "    if failure is not None:\n"
            "        request.mark_failed(str(failure))\n"
        )

        found = findings(source, NOTE_METHODS)

        self.assertEqual(len(found), 1)
        self.assertIn(gate.SERVES_EXCEPTION_TEXT_TO_A_FIELD, found[0])

    def test_a_fixed_note_is_not_a_finding(self):
        source = (
            "def run():\n"
            "    try:\n"
            "        x()\n"
            "    except Exception as e:\n"
            "        logger.error(e)\n"
            "        request.mark_failed(EXECUTION_FAILED)\n"
        )

        self.assertEqual(findings(source, NOTE_METHODS), [])

    def test_an_allowed_receiver_is_not_a_finding(self):
        found = findings(
            "try:\n    x()\nexcept Exception as e:\n    tx_record.mark_failed(str(e))\n", NOTE_METHODS
        )

        self.assertEqual(found, [])

    def test_a_method_no_client_serializer_backs_is_not_a_finding(self):
        found = findings(
            "try:\n    x()\nexcept Exception as e:\n    audit.write_note(str(e))\n", NOTE_METHODS
        )

        self.assertEqual(found, [])

    def test_the_same_call_is_reported_once_rather_than_twice(self):
        source = (
            "def run():\n"
            "    try:\n"
            "        x()\n"
            "    except Exception as e:\n"
            "        failure = e\n"
            "        request.mark_failed(str(failure))\n"
        )

        self.assertEqual(len(findings(source, NOTE_METHODS)), 1)


class TheMethodSetIsDerivedFromTheSourceRatherThanListed(unittest.TestCase):

    def test_a_field_a_serializer_exposes_puts_its_writer_in_the_set(self):
        self.assertIn("mark_failed", gate.note_methods_a_client_reads())

    def test_a_model_whose_serializer_hides_the_field_is_matched_by_model_not_by_name(self):
        exposed = gate.fields_each_model_exposes()

        self.assertIn("review_notes", exposed.get("CapitalIncreaseRequest", set()))
        self.assertNotIn("MintRequest", exposed)
