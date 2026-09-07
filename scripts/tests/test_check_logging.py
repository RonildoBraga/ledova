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


class BackendBodyRule(unittest.TestCase):
    def rules(self, source):
        return [rule for _, rule, _ in gate.python_findings(source)]

    def test_a_whole_response_in_an_fstring_is_refused(self):
        self.assertEqual(self.rules('logger.info(f"Applicant data for {applicant_id}: {response}")'), [gate.LOG_BODY])

    def test_the_offending_call_is_named_and_located(self):
        source = 'import logging\nlogger = logging.getLogger(__name__)\nlogger.info(f"{response}")\n'
        self.assertEqual(gate.python_findings(source), [(3, gate.LOG_BODY, "logger.info(... response ...)")])

    def test_a_named_field_of_the_response_is_allowed(self):
        self.assertEqual(self.rules('logger.info(f"{applicant_id}: {response.status_code}")'), [])

    def test_the_review_answer_read_through_a_helper_is_allowed(self):
        self.assertEqual(self.rules('logger.info(f"{applicant_id}: {self._review_answer(response)}")'), [])

    def test_the_response_text_attribute_is_refused(self):
        self.assertEqual(self.rules('logger.error(f"API Error: {response.status_code} - {response.text}")'), [gate.LOG_BODY])

    def test_a_parsed_json_body_is_refused(self):
        self.assertEqual(self.rules('logger.error(f"{response.json()}")'), [gate.LOG_BODY])

    def test_a_details_subobject_is_refused(self):
        self.assertEqual(self.rules('logger.warning(f"failed: {ticket.get(\'details\')}")'), [gate.LOG_BODY])

    def test_the_error_code_inside_the_details_is_allowed(self):
        self.assertEqual(self.rules('logger.warning(f"failed: {reason.get(\'error\')}")'), [])

    def test_a_positional_argument_is_refused(self):
        self.assertEqual(self.rules('logger.info("provider said %s", payload)'), [gate.LOG_BODY])

    def test_str_around_the_body_does_not_get_it_past_the_gate(self):
        self.assertEqual(self.rules('logger.info(f"{str(webhook_data)}")'), [gate.LOG_BODY])

    def test_json_dumps_around_the_body_does_not_get_it_past_the_gate(self):
        self.assertEqual(self.rules('logger.info(f"{json.dumps(response)}")'), [gate.LOG_BODY])

    def test_format_around_the_body_does_not_get_it_past_the_gate(self):
        self.assertEqual(self.rules('logger.info("provider said {}".format(error_body))'), [gate.LOG_BODY])

    def test_a_body_handed_to_something_that_is_not_logging_is_not_the_gate_s_business(self):
        self.assertEqual(self.rules("cache.set(key, response)"), [])

    def test_a_provider_error_message_string_is_deliberately_ungated(self):
        self.assertEqual(self.rules('logger.warning(f"failed: {ticket.get(\'message\')}")'), [])


class RepositoryScan(unittest.TestCase):
    def test_the_tree_is_clean(self):
        violations, checked = gate.scan()
        self.assertEqual(violations, [])
        self.assertGreater(checked, 0)


if __name__ == "__main__":
    unittest.main()


class ClientBodyRule(unittest.TestCase):

    def test_a_template_reaching_into_the_request_body_is_refused(self):
        findings = gate.script_findings("console.error(`API failed: ${error.config?.data}`);")
        self.assertEqual([f[1] for f in findings], [gate.CONSOLE_BODY])

    def test_every_body_attribute_is_refused(self):
        for attribute in ("body", "config", "data", "params", "request", "response"):
            findings = gate.script_findings("console.warn(`x ${e.%s}`);" % attribute)
            self.assertEqual([f[1] for f in findings], [gate.CONSOLE_BODY], attribute)

    def test_a_narrow_interpolation_is_allowed(self):
        for span in ("${status}", "${error.code}", "${response.status}", "${describeFailure(error)}"):
            self.assertEqual(gate.script_findings("console.error(`x %s`);" % span), [])

    def test_a_plain_literal_is_allowed(self):
        self.assertEqual(gate.script_findings("console.error('plain message');"), [])
