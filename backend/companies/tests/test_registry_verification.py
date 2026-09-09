from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.db import connections
from django.test import TransactionTestCase, override_settings
from django.urls import reverse
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from companies.admin.company import CompanyAdmin
from companies.exceptions import (
    InvalidStatusTransitionException,
    OfficeholderAttestationRequiredException,
    RegistryVerificationRequiredException,
)
from companies.models import (
    Company,
    CompanyStatus,
    CompanyType,
    RegistryCheckPurpose,
    RegistryCheckStatus,
)
from companies.serializers.company import CompanyUpdateSerializer
from companies.services import transition_company
from companies.services.editing import update_company
from companies.services.registry import begin_registry_check, complete_registry_check
from companies.tests.registry_fixtures import DECLARATION, matching_observation
from integrations.abr.client import RegistryObservation, lookup_company
from shared.db import atomic, current_alias

User = get_user_model()
PROVIDER = "companies.services.registry.lookup_company"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "private": {"BACKEND": "shared.storage.PrivateMediaStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
ACTIVE_ENTRIES = (
    (CompanyStatus.APPROVED, "activate"),
    (CompanyStatus.WARNING, "resolve_warning"),
    (CompanyStatus.SUSPENDED, "reinstate"),
)


@override_settings(STORAGES=STORAGES, ABR_AUTH_GUID="")
class CompanyRegistryVerificationTest(TransactionTestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="registry-owner@example.test")
        self.operator = User.objects.create_superuser(
            email="registry-operator@example.test", password="synthetic-password"
        )
        self.company = Company.objects.create(owner=self.owner, name="Synthetic Example Pty Ltd", acn="123456780")
        self.client = APIClient()
        self.lookup = patch(PROVIDER, return_value=matching_observation(self.company)).start()
        patch("companies.services.company.send_push_notification").start()
        self.addCleanup(patch.stopall)
        self.api_url = f"/api/v1/companies/{self.company.pk}/"
        self.admin_url = reverse("admin:companies_company_change", args=[self.company.pk])

    def set_status(self, status):
        Company.objects.filter(pk=self.company.pk).update(status=status)
        self.company.refresh_from_db()

    def transition(self, method, **kwargs):
        self.company = transition_company(self.company, method, actor=self.operator, **kwargs)
        return self.company

    def approve(self):
        self.set_status(CompanyStatus.REVIEW)
        self.transition("approve", declaration=DECLARATION)

    def admin_action(self, action):
        return reverse("admin:companies_company_transition", args=[self.company.pk, action])

    def status_post(self, status, **data):
        self.client.force_authenticate(self.operator)
        return self.client.post(f"{self.api_url}status/", {"status": status, **data}, format="json")

    def test_start_review_records_input_attempt_and_entity_outside_a_transaction(self):
        self.set_status(CompanyStatus.SUBMITTED)

        def observe(**inputs):
            self.assertFalse(connections[current_alias()].in_atomic_block)
            current = Company.objects.get(pk=self.company.pk)
            self.assertEqual(current.status, CompanyStatus.REVIEW)
            self.assertEqual(current.registry_status, RegistryCheckStatus.PENDING)
            self.assertIsNone(current.registry_check.completed_at)
            self.assertEqual(inputs, {"acn": "123456780", "abn": ""})
            return matching_observation(current)

        self.lookup.side_effect = observe
        response = self.status_post("review")

        self.assertEqual(response.status_code, 200, response.data)
        self.company.refresh_from_db()
        check = self.company.registry_checks.get()
        self.assertEqual(check.status, RegistryCheckStatus.PASSED)
        self.assertEqual(check.purpose, RegistryCheckPurpose.REVIEW)
        self.assertEqual(check.initiated_by, self.operator)
        self.assertEqual(check.requested_name, self.company.name)
        self.assertEqual(check.entity_name, self.company.name)
        self.assertEqual(check.entity_status, "Active")
        self.assertGreaterEqual(check.completed_at, check.started_at)

    def test_review_refuses_an_outer_transaction_before_any_attempt_or_http(self):
        self.set_status(CompanyStatus.SUBMITTED)
        with self.assertRaises(RuntimeError):
            with atomic():
                self.transition("start_review")
        self.lookup.assert_not_called()
        self.assertFalse(self.company.registry_checks.exists())

    def test_approval_needs_explicit_named_attestation_but_may_precede_registry_pass(self):
        self.set_status(CompanyStatus.REVIEW)
        for declaration in (
            {},
            {**DECLARATION, "attest_officeholder": False},
            {**DECLARATION, "declarant_name": ""},
            {**DECLARATION, "board_resolution_reference": ""},
        ):
            with self.subTest(declaration=declaration):
                with self.assertRaises(OfficeholderAttestationRequiredException):
                    self.transition("approve", declaration=declaration)
                self.company.refresh_from_db()
                self.assertEqual(self.company.status, CompanyStatus.REVIEW)
                self.assertIsNone(self.company.officeholder_attested_at)
        self.transition("approve", declaration=DECLARATION)
        self.assertEqual(self.company.status, CompanyStatus.APPROVED)
        self.assertEqual(self.company.officeholder_attested_by, self.operator)
        self.assertTrue(self.company.has_officeholder_attestation)
        self.assertEqual(self.company.registry_status, RegistryCheckStatus.PENDING)
        self.lookup.assert_not_called()

    def test_every_active_entry_requires_fresh_matching_registry_and_attestation(self):
        for predecessor, method in ACTIVE_ENTRIES:
            with self.subTest(method=method):
                self.set_status(predecessor)
                with self.assertRaises(OfficeholderAttestationRequiredException):
                    self.transition(method)
                self.transition(method, declaration=DECLARATION)
                self.assertEqual(self.company.status, CompanyStatus.ACTIVE)
                check = self.company.registry_check
                self.assertEqual(check.purpose, RegistryCheckPurpose.ACTIVATION)
                self.set_status(predecessor)
                with self.assertRaises(RegistryVerificationRequiredException):
                    getattr(self.company, method)()
                self.company.officeholder_attestation = {}
                self.company.save(update_fields=["officeholder_attestation"])
        self.assertEqual(self.lookup.call_count, len(ACTIVE_ENTRIES))

    def test_timeout_after_a_pass_refuses_activation_and_retains_the_failed_attempt(self):
        self.approve()
        self.transition("retry_registry")
        previous = self.company.registry_check
        self.assertEqual(previous.status, RegistryCheckStatus.PASSED)
        self.lookup.return_value = RegistryObservation(reason="timeout")

        response = self.status_post("active")

        self.assertEqual(response.status_code, 400, response.data)
        self.company.refresh_from_db()
        self.assertEqual(self.company.status, CompanyStatus.APPROVED)
        self.assertEqual(self.company.registry_status, RegistryCheckStatus.PENDING)
        self.assertEqual(self.company.registry_reason, "timeout")
        self.assertIsNotNone(self.company.registry_check.completed_at)
        self.assertNotEqual(self.company.registry_check, previous)
        previous.refresh_from_db()
        self.assertEqual(previous.status, RegistryCheckStatus.PASSED)
        self.assertEqual(self.company.registry_checks.count(), 2)
        self.lookup.return_value = matching_observation(self.company)
        self.assertEqual(self.status_post("active").status_code, 200)

    def test_a_new_pending_retry_immediately_replaces_the_previous_pass(self):
        self.approve()
        self.transition("retry_registry")

        def retry(**kwargs):
            current = Company.objects.get(pk=self.company.pk)
            self.assertEqual(current.registry_status, RegistryCheckStatus.PENDING)
            self.assertIsNone(current.registry_checked_at)
            return RegistryObservation(reason="unavailable")

        self.lookup.side_effect = retry
        self.transition("retry_registry")
        self.assertEqual(self.company.registry_status, RegistryCheckStatus.PENDING)

    def test_unconfigured_review_records_pending_without_http(self):
        with patch(PROVIDER, side_effect=lookup_company):
            with patch("integrations.abr.client.requests.post") as http:
                self.set_status(CompanyStatus.SUBMITTED)
                self.transition("start_review")
                http.assert_not_called()
        self.assertEqual(self.company.registry_status, RegistryCheckStatus.PENDING)
        self.assertEqual(self.company.registry_check.reason, "unconfigured")

    def test_registry_refusals_have_a_matching_positive_control(self):
        self.approve()
        observation = matching_observation(self.company)
        cases = (
            (replace(observation, acn="987654320"), "failed", "identifier_mismatch"),
            (replace(observation, entity_name="Different Pty Ltd"), "failed", "name_mismatch"),
            (replace(observation, entity_name="Synthetic Example"), "failed", "name_mismatch"),
            (replace(observation, entity_status="Cancelled"), "failed", "cancelled"),
            (replace(observation, entity_status="Unknown"), "pending", "unknown_status"),
            (replace(observation, entity_name=""), "pending", "incomplete_identity"),
            (replace(observation, acn=""), "pending", "incomplete_identity"),
            (RegistryObservation(reason="not_found"), "failed", "not_found"),
            (RegistryObservation(reason="invalid_response"), "pending", "invalid_response"),
        )
        for reply, status, reason in cases:
            with self.subTest(reason=reason, reply=reply):
                self.lookup.return_value = reply
                with self.assertRaises(RegistryVerificationRequiredException):
                    self.transition("activate")
                self.company.refresh_from_db()
                self.assertEqual(self.company.status, CompanyStatus.APPROVED)
                self.assertEqual((self.company.registry_status, self.company.registry_reason), (status, reason))
        self.lookup.return_value = replace(observation, entity_name="  SYNTHETIC   EXAMPLE pty Ltd  ")
        self.transition("activate")
        self.assertEqual(self.company.status, CompanyStatus.ACTIVE)

    def test_each_company_type_requires_its_corresponding_registry_type_before_activation(self):
        for company_type, expected, contradictory in (
            (CompanyType.PROPRIETARY, "PRV", "PUB"),
            (CompanyType.PUBLIC, "PUB", "PRV"),
            (CompanyType.UNLISTED_PUBLIC, "PUB", "PRV"),
        ):
            with self.subTest(company_type=company_type):
                Company.objects.filter(pk=self.company.pk).update(company_type=company_type)
                self.approve()
                observation = matching_observation(self.company)
                self.lookup.return_value = replace(observation, entity_type=contradictory)

                with self.assertRaises(RegistryVerificationRequiredException):
                    self.transition("activate")

                self.company.refresh_from_db()
                self.assertEqual(self.company.status, CompanyStatus.APPROVED)
                self.assertEqual(self.company.registry_status, RegistryCheckStatus.FAILED)
                self.assertEqual(self.company.registry_reason, "entity_type_mismatch")
                self.assertEqual(self.company.registry_check.entity_type, contradictory)
                self.lookup.return_value = replace(observation, entity_type=expected)
                self.transition("activate")
                self.assertEqual(self.company.status, CompanyStatus.ACTIVE)
                self.assertEqual(self.company.registry_check.entity_type, expected)

    def test_missing_and_unsupported_registry_types_remain_pending_and_refuse_activation(self):
        self.approve()
        observation = matching_observation(self.company)
        for entity_type, reason in (
            ("", "incomplete_identity"),
            ("UNKNOWN", "unknown_entity_type"),
            ("PRV PUB", "unknown_entity_type"),
            ("IND", "unknown_entity_type"),
        ):
            with self.subTest(entity_type=entity_type):
                self.set_status(CompanyStatus.APPROVED)
                self.lookup.return_value = replace(observation, entity_type=entity_type)
                with self.assertRaises(RegistryVerificationRequiredException):
                    self.transition("activate")
                self.company.refresh_from_db()
                self.assertEqual(self.company.status, CompanyStatus.APPROVED)
                self.assertEqual(self.company.registry_status, RegistryCheckStatus.PENDING)
                self.assertEqual(self.company.registry_reason, reason)
                self.assertEqual(self.company.registry_check.entity_type, entity_type)
        self.set_status(CompanyStatus.APPROVED)
        self.lookup.return_value = observation
        self.transition("activate")
        self.assertEqual(self.company.status, CompanyStatus.ACTIVE)

    def test_a_bulk_review_post_performs_no_lookups_and_individual_review_still_works(self):
        self.set_status(CompanyStatus.SUBMITTED)
        second = Company.objects.create(
            owner=self.owner, name="Second Pty Ltd", acn="987654320", status=CompanyStatus.SUBMITTED
        )
        self.client.force_login(self.operator)
        changelist = reverse("admin:companies_company_changelist")
        response = self.client.post(
            changelist,
            {"action": "start_review_action", "_selected_action": [str(self.company.pk), str(second.pk)], "index": 0},
        )

        self.assertEqual(response.status_code, 302)
        self.lookup.assert_not_called()
        self.company.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(self.company.status, CompanyStatus.SUBMITTED)
        self.assertEqual(second.status, CompanyStatus.SUBMITTED)
        self.assertFalse(self.company.registry_checks.exists())
        self.assertFalse(second.registry_checks.exists())
        self.assertNotContains(self.client.get(changelist), "Start review for selected submitted applications")

        page = self.client.get(self.admin_action("start-review"))
        self.assertEqual(page.status_code, 200)
        self.lookup.assert_not_called()
        response = self.client.post(self.admin_action("start-review"), {"confirm": True})
        self.assertEqual(response.status_code, 302)
        self.lookup.assert_called_once_with(acn=self.company.acn, abn="")
        self.company.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(self.company.status, CompanyStatus.REVIEW)
        self.assertEqual(self.company.registry_status, RegistryCheckStatus.PASSED)
        self.assertEqual(second.status, CompanyStatus.SUBMITTED)
        self.assertFalse(second.registry_checks.exists())

    def test_supplied_abn_must_match_and_acn_fallback_does_not_fill_application_abn(self):
        self.approve()
        self.transition("activate")
        self.assertEqual(self.company.abn, "")
        self.assertEqual(self.company.registry_check.registry_abn, "99123456780")
        self.set_status(CompanyStatus.APPROVED)
        Company.objects.filter(pk=self.company.pk).update(abn="98123456780")
        self.company.refresh_from_db()
        with self.assertRaises(RegistryVerificationRequiredException):
            self.transition("activate", declaration=DECLARATION)
        self.company.refresh_from_db()
        self.assertEqual(self.company.registry_reason, "identifier_mismatch")

    def test_out_of_order_completion_keeps_the_newer_observation_current(self):
        self.approve()
        with atomic():
            first = begin_registry_check(self.company, RegistryCheckPurpose.RETRY, self.operator)
            second = begin_registry_check(self.company, RegistryCheckPurpose.RETRY, self.operator)
        complete_registry_check(second, RegistryObservation(reason="timeout"))
        complete_registry_check(first, matching_observation(self.company))
        self.company.refresh_from_db()
        self.assertEqual(self.company.registry_check_id, second.pk)
        self.assertEqual(self.company.registry_status, RegistryCheckStatus.PENDING)
        first.refresh_from_db()
        self.assertEqual(first.status, RegistryCheckStatus.PASSED)

    def test_identity_changed_away_and_back_cannot_reuse_an_older_lookup(self):
        self.set_status(CompanyStatus.INFO_REQUIRED)
        with atomic():
            check = begin_registry_check(self.company, RegistryCheckPurpose.RETRY, self.operator)
        update_company(self.company, {"name": "Correction Pty Ltd"})
        update_company(self.company, {"name": self.company.name})
        complete_registry_check(check, matching_observation(self.company))
        self.company.refresh_from_db()
        self.assertEqual(self.company.registry_status, RegistryCheckStatus.PENDING)
        self.assertEqual(self.company.registry_reason, "identity_changed")
        check.refresh_from_db()
        self.assertEqual(check.status, RegistryCheckStatus.PASSED)

    def test_concurrent_lifecycle_change_defeats_a_passing_activation_lookup(self):
        self.approve()

        def observe(**kwargs):
            current = Company.objects.get(pk=self.company.pk)
            transition_company(current, "delist", reason="Concurrent decision")
            return matching_observation(current)

        self.lookup.side_effect = observe
        with self.assertRaises(InvalidStatusTransitionException):
            self.transition("activate")
        self.company.refresh_from_db()
        self.assertEqual(self.company.status, CompanyStatus.DELISTED)
        self.assertEqual(self.company.registry_status, RegistryCheckStatus.PENDING)
        self.assertEqual(self.company.registry_check.status, RegistryCheckStatus.PASSED)

    def test_attestation_snapshot_refuses_a_changed_declaration_or_identity(self):
        self.approve()
        for field, changed in (
            ("declarant_name", "Other declarant"),
            ("board_resolution_reference", "BR-002"),
            ("name", "Other name"),
        ):
            original = getattr(self.company, field)
            setattr(self.company, field, changed)
            self.assertFalse(self.company.has_officeholder_attestation)
            with self.assertRaises(OfficeholderAttestationRequiredException):
                self.company.activate()
            setattr(self.company, field, original)
        self.assertTrue(self.company.has_officeholder_attestation)

    def test_concurrent_identity_change_cannot_activate_from_the_previous_name(self):
        self.approve()
        previous_identity = matching_observation(self.company)

        def observe(**kwargs):
            Company.objects.filter(pk=self.company.pk).update(name="Changed during lookup Pty Ltd")
            return previous_identity

        self.lookup.side_effect = observe
        with self.assertRaises(OfficeholderAttestationRequiredException):
            self.transition("activate")
        self.company.refresh_from_db()
        self.assertEqual(self.company.status, CompanyStatus.APPROVED)
        self.assertEqual(self.company.registry_status, RegistryCheckStatus.PENDING)
        self.assertEqual(self.company.registry_check.status, RegistryCheckStatus.PASSED)

    def test_admin_status_field_cannot_bypass_activation(self):
        self.approve()
        self.client.force_login(self.operator)
        page = self.client.get(self.admin_url)
        form = page.context["adminform"].form
        self.assertNotIn("status", form.fields)
        payload = {name: form[name].value() or "" for name in form.fields}
        for inline in page.context["inline_admin_formsets"]:
            for field in inline.formset.management_form:
                payload[field.html_name] = field.value()
            for inline_form in inline.formset.forms:
                for field in inline_form.hidden_fields():
                    payload[field.html_name] = field.value() or ""
        payload.update(status="active", description="Description saved")
        response = self.client.post(self.admin_url, payload)
        self.assertEqual(response.status_code, 302)
        self.company.refresh_from_db()
        self.assertEqual(self.company.description, "Description saved")
        self.assertEqual(self.company.status, CompanyStatus.APPROVED)
        self.assertFalse(self.company.registry_checks.exists())

    def test_stale_api_and_admin_description_saves_preserve_suspension_and_new_attestation(self):
        self.approve()
        self.transition("activate")
        stale_api = Company.objects.get(pk=self.company.pk)
        stale_admin = Company.objects.get(pk=self.company.pk)
        serializer = CompanyUpdateSerializer(stale_api, data={"description": "API description"}, partial=True)
        serializer.is_valid(raise_exception=True)
        self.transition("suspend", reason="Concurrent suspension")
        self.lookup.return_value = RegistryObservation(reason="timeout")
        with self.assertRaises(RegistryVerificationRequiredException):
            self.transition("reinstate", declaration={**DECLARATION, "board_resolution_reference": "New BR-002"})
        self.company.refresh_from_db()
        evidence = (
            self.company.registry_check_id,
            self.company.officeholder_attestation,
            self.company.lifecycle_revision,
        )

        serializer.save()
        model_admin = CompanyAdmin(Company, AdminSite())
        model_admin.save_model(
            None,
            stale_admin,
            SimpleNamespace(changed_data=["description"], cleaned_data={"description": "Admin description"}),
            True,
        )

        self.company.refresh_from_db()
        self.assertEqual(self.company.status, CompanyStatus.SUSPENDED)
        self.assertEqual(self.company.description, "Admin description")
        self.assertEqual(
            (self.company.registry_check_id, self.company.officeholder_attestation, self.company.lifecycle_revision),
            evidence,
        )

    def test_stale_draft_api_and_admin_identity_edits_are_refused_after_review(self):
        serializer = CompanyUpdateSerializer(self.company, data={"name": "Edited Pty Ltd"}, partial=True)
        serializer.is_valid(raise_exception=True)
        stale = Company.objects.get(pk=self.company.pk)
        self.transition("submit", submitted_by=self.owner)
        self.transition("start_review")
        with self.assertRaises(ValidationError):
            serializer.save()
        model_admin = CompanyAdmin(Company, AdminSite())
        with self.assertRaises(ValidationError):
            model_admin.save_model(
                None, stale, SimpleNamespace(changed_data=["name"], cleaned_data={"name": "Edited Pty Ltd"}), True
            )
        self.company.refresh_from_db()
        self.assertEqual(self.company.name, "Synthetic Example Pty Ltd")
        self.transition("request_info", reason="Correct the registered name")
        updated = update_company(stale, {"name": "Edited Pty Ltd"})
        self.assertEqual(updated.name, "Edited Pty Ltd")
        self.assertEqual(updated.registry_status, RegistryCheckStatus.PENDING)

    def test_active_legacy_identity_is_locked_without_revoking_existing_status(self):
        self.set_status(CompanyStatus.ACTIVE)
        self.client.force_authenticate(self.owner)
        response = self.client.patch(self.api_url, {"name": "Different Pty Ltd"}, format="json")
        self.assertEqual(response.status_code, 400, response.data)
        response = self.client.patch(self.api_url, {"trading_name": "New display name"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.company.refresh_from_db()
        self.assertEqual(self.company.status, CompanyStatus.ACTIVE)
        self.assertEqual(self.company.name, "Synthetic Example Pty Ltd")
        self.assertIsNone(self.company.officeholder_attested_at)
        self.lookup.return_value = RegistryObservation(reason="timeout")
        self.transition("retry_registry")
        self.assertEqual(self.company.status, CompanyStatus.ACTIVE)
        for entity_type, status in (("PUB", RegistryCheckStatus.FAILED), ("", RegistryCheckStatus.PENDING)):
            self.lookup.return_value = replace(matching_observation(self.company), entity_type=entity_type)
            self.transition("retry_registry")
            self.assertEqual(self.company.registry_status, status)
            self.assertEqual(self.company.status, CompanyStatus.ACTIVE)

    def test_legacy_active_entries_have_a_supported_admin_attestation_recovery(self):
        self.client.force_login(self.operator)
        for predecessor, method in ACTIVE_ENTRIES:
            action = method.replace("_", "-")
            with self.subTest(action=action):
                self.set_status(predecessor)
                Company.objects.filter(pk=self.company.pk).update(officeholder_attestation={})
                page = self.client.get(self.admin_action(action))
                self.assertContains(page, "Named officeholder making the declaration")
                self.assertEqual(Company.objects.get(pk=self.company.pk).status, predecessor)
                self.lookup.return_value = RegistryObservation(reason="timeout")
                refused = self.client.post(self.admin_action(action), {"confirm": True, **DECLARATION})
                self.assertEqual(refused.status_code, 302)
                self.company.refresh_from_db()
                self.assertEqual(self.company.status, predecessor)
                self.assertTrue(self.company.has_officeholder_attestation)
                self.assertEqual(self.company.registry_reason, "timeout")
                self.lookup.return_value = matching_observation(self.company)
                allowed = self.client.post(self.admin_action(action), {"confirm": True})
                self.assertEqual(allowed.status_code, 302)
                self.company.refresh_from_db()
                self.assertEqual(self.company.status, CompanyStatus.ACTIVE)

    def test_review_details_are_private_and_ordinary_writes_cannot_forge_them(self):
        self.approve()
        self.transition("retry_registry")
        self.client.force_login(self.operator)
        page = self.client.get(self.admin_action("activate"))
        self.assertContains(page, self.operator.email)
        self.assertContains(page, self.company.name)
        page = self.client.get(self.admin_url)
        self.assertContains(page, DECLARATION["declarant_name"])
        self.assertContains(page, DECLARATION["board_resolution_reference"])
        self.client.logout()
        self.client.force_authenticate(self.owner)
        for path in (self.api_url, f"{self.api_url}application-status/", "/api/v1/companies/"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertNotIn(DECLARATION["declarant_name"], str(response.data))
            self.assertNotIn(DECLARATION["board_resolution_reference"], str(response.data))
            self.assertNotIn(self.operator.email, str(response.data))
        response = self.client.patch(
            self.api_url,
            {
                "registry_status": "passed",
                "officeholder_attestation": {},
                "declarant_name": "Forged",
                "description": "Owner description",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.company.refresh_from_db()
        self.assertEqual(self.company.declarant_name, DECLARATION["declarant_name"])
        self.assertTrue(self.company.has_officeholder_attestation)
        self.assertEqual(self.company.description, "Owner description")
