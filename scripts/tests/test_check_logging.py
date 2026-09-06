#!/usr/bin/env python3
"""Prove the logging privacy gate fires, and prove where it deliberately does not."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "check-logging.py"
_spec = importlib.util.spec_from_file_location("check_logging", SCRIPT)
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)


class ConsoleArgumentRule(unittest.TestCase):
    def rules(self, source):
        return [rule for _, rule, _ in gate.script_findings(source)]

    def test_an_error_object_passed_beside_a_message_is_refused(self):
        self.assertEqual(
            self.rules("console.error('Account creation failed:', error);"),
            [gate.CONSOLE_ARGUMENT],
        )

    def test_the_offending_argument_is_named_and_located(self):
        source = "const a = 1;\nconsole.error('Sign-in failed:', err);\n"
        self.assertEqual(gate.script_findings(source), [(2, gate.CONSOLE_ARGUMENT, "console.error(err)")])

    def test_a_template_literal_describing_the_failure_is_allowed(self):
        self.assertEqual(self.rules("console.error(`Account creation failed: ${describeFailure(error)}`);"), [])

    def test_several_string_literals_are_allowed(self):
        self.assertEqual(self.rules("console.log('one', 'two');"), [])

    def test_a_call_with_no_arguments_is_allowed(self):
        self.assertEqual(self.rules("console.error();"), [])

    def test_a_bare_identifier_is_refused_even_when_it_holds_a_string(self):
        self.assertEqual(self.rules("console.error(message);"), [gate.CONSOLE_ARGUMENT])

    def test_stringify_inside_a_template_is_refused(self):
        self.assertEqual(
            self.rules("console.log(`Delete failed: ${JSON.stringify(err.response.data)}`);"),
            [gate.CONSOLE_STRINGIFY],
        )

    def test_a_template_spanning_lines_with_a_nested_call_is_allowed(self):
        source = "console.error(`[Boundary] ${name}: ${describe(error, {deep: true})}\n${stack}`);"
        self.assertEqual(self.rules(source), [])

    def test_every_offending_argument_of_one_call_is_reported(self):
        self.assertEqual(
            self.rules("console.log('[Delete]', status, JSON.stringify(body), err.message);"),
            [gate.CONSOLE_ARGUMENT] * 3,
        )

    def test_a_console_call_quoted_inside_a_string_is_not_a_call(self):
        self.assertEqual(self.rules("const advice = 'never write console.error(error) here';"), [])

    def test_a_console_call_inside_a_comment_is_not_a_call(self):
        self.assertEqual(self.rules("// console.error(error)\nconsole.error('fine');"), [])

    def test_a_regex_literal_matching_a_console_call_is_not_a_call(self):
        self.assertEqual(self.rules("const pattern = /console\\.error\\(error\\)/;\nconsole.error('fine');"), [])

    def test_a_division_is_not_read_as_a_regex(self):
        self.assertEqual(self.rules("const ratio = width / height;\nconsole.error(raw);"), [gate.CONSOLE_ARGUMENT])

    def test_a_method_that_is_not_a_console_method_is_ignored(self):
        self.assertEqual(self.rules("console.groupCollapsed(error);"), [])

    def test_warn_is_checked_the_same_way_as_error(self):
        self.assertEqual(self.rules("console.warn(payload);"), [gate.CONSOLE_ARGUMENT])


class BackendLogRule(unittest.TestCase):
    def rules(self, source):
        return [rule for _, rule, _ in gate.python_findings(source)]

    def test_an_email_attribute_in_an_fstring_is_refused(self):
        self.assertEqual(self.rules('logger.info(f"User {user.email} authenticated")'), [gate.LOG_PRIVATE])

    def test_the_offending_call_is_named_and_located(self):
        source = 'import logging\nlogger = logging.getLogger(__name__)\nlogger.info(f"{user.email}")\n'
        self.assertEqual(gate.python_findings(source), [(3, gate.LOG_PRIVATE, "logger.info(... .email ...)")])

    def test_a_primary_key_is_allowed(self):
        self.assertEqual(self.rules('logger.info(f"User {user.pk} authenticated")'), [])

    def test_a_percent_style_argument_is_refused(self):
        self.assertEqual(self.rules('logger.warning("User %s failed", user.email)'), [gate.LOG_PRIVATE])

    def test_a_keyword_argument_is_refused(self):
        self.assertEqual(self.rules('logger.error("failed", extra={"actor": user.email})'), [gate.LOG_PRIVATE])

    def test_a_bare_email_variable_is_refused(self):
        self.assertEqual(self.rules('logger.info(f"Verification sent to {email}")'), [gate.LOG_PRIVATE])

    def test_a_constant_string_subscript_is_refused(self):
        self.assertEqual(self.rules('logger.info(f"{payload[\'email\']}")'), [gate.LOG_PRIVATE])

    def test_a_password_is_refused(self):
        self.assertEqual(self.rules('logger.debug(f"{credentials.password}")'), [gate.LOG_PRIVATE])

    def test_a_push_token_fragment_is_refused(self):
        self.assertEqual(self.rules('logger.info(f"{device.push_token[:30]}...")'), [gate.LOG_PRIVATE])

    def test_a_dotted_logger_is_checked(self):
        self.assertEqual(self.rules('self.logger.exception(f"{user.email}")'), [gate.LOG_PRIVATE])

    def test_an_unrelated_token_attribute_is_allowed(self):
        self.assertEqual(self.rules('logger.info(f"Deployed {token.symbol} at {address}")'), [])

    def test_a_call_that_is_not_logging_is_not_the_gate_s_business(self):
        self.assertEqual(self.rules("send_mail(subject, body, sender, [user.email])"), [])

    def test_print_is_deliberately_ungated(self):
        self.assertEqual(self.rules('print(f"{user.email}")'), [])

    def test_unparseable_python_is_reported_rather_than_skipped(self):
        findings = gate.python_findings("def broken(:\n")
        self.assertEqual([rule for _, rule, _ in findings], [gate.LOG_PRIVATE])


class RepositoryScan(unittest.TestCase):
    def test_the_tree_is_clean(self):
        violations, checked = gate.scan()
        self.assertEqual(violations, [])
        self.assertGreater(checked, 0)


if __name__ == "__main__":
    unittest.main()
