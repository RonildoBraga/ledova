from types import SimpleNamespace
from unittest.mock import patch

import requests
from django.test import SimpleTestCase, override_settings

from integrations.abr.client import (
    ABR_NAMESPACE,
    ABR_SERVICE,
    MAX_RESPONSE_BYTES,
    lookup_company,
    parse_observation,
)


def registry_xml(entity="", exception="", retrieval="2026-09-01T10:30:00", version="202001"):
    result = (
        "<exception><exceptionCode>SEARCH</exceptionCode>"
        f"<exceptionDescription>{exception}</exceptionDescription></exception>"
        if exception
        else f"<businessEntity{version}>{entity}</businessEntity{version}>"
    )
    return f"""<ABRPayloadSearchResults xmlns="{ABR_NAMESPACE}">
        <request><authenticationGUID>synthetic-guid-must-not-be-retained</authenticationGUID></request>
        <response><dateRegisterLastUpdated>2026-09-01</dateRegisterLastUpdated>
        <dateTimeRetrieved>{retrieval}</dateTimeRetrieved>
        {result}
        </response></ABRPayloadSearchResults>""".encode()


ENTITY = """
    <ABN><identifierValue>99123456780</identifierValue><isCurrentIndicator>Y</isCurrentIndicator></ABN>
    <ASICNumber>123456780</ASICNumber>
    <mainName><organisationName>Synthetic Example Pty Ltd</organisationName>
    <effectiveFrom>2025-01-01</effectiveFrom></mainName>
    <entityType><entityTypeCode>PRV</entityTypeCode></entityType>
    <entityStatus><entityStatusCode>Active</entityStatusCode><effectiveFrom>2025-01-01</effectiveFrom></entityStatus>
"""


class ABRResponseTest(SimpleTestCase):
    def test_both_supported_versions_retain_selected_entity_fields_and_unzoned_provider_time(self):
        for version in ("202001", "201408"):
            with self.subTest(version=version):
                observation = parse_observation(registry_xml(ENTITY, version=version))
                self.assertEqual(observation.reason, "")
                self.assertEqual(observation.acn, "123456780")
                self.assertEqual(observation.abn, "99123456780")
                self.assertEqual(observation.entity_name, "Synthetic Example Pty Ltd")
                self.assertEqual(observation.entity_status, "Active")
                self.assertEqual(observation.effective_from.isoformat(), "2025-01-01")
                self.assertEqual(observation.retrieved_at, "2026-09-01T10:30:00")
                self.assertEqual(observation.register_updated_at.isoformat(), "2026-09-01")
                self.assertNotIn("synthetic-guid", repr(observation))

    def test_only_authoritative_not_found_is_a_failed_lookup(self):
        self.assertEqual(parse_observation(registry_xml(exception="No records found")).reason, "not_found")
        for description in ("Authentication GUID invalid", "Provider unavailable", "Unexpected provider text"):
            self.assertEqual(parse_observation(registry_xml(exception=description)).reason, "provider_error")

    def test_malformed_ambiguous_oversized_and_historical_responses_never_supply_identity(self):
        for payload in (
            b"broken XML",
            b"x" * (MAX_RESPONSE_BYTES + 1),
            b"<different />",
            registry_xml(ENTITY + "<mainName><organisationName>Other Pty Ltd</organisationName></mainName>"),
            registry_xml(ENTITY.replace("123456780</ASICNumber>", "bad</ASICNumber>")),
            registry_xml(ENTITY.replace("99123456780", "123")),
            registry_xml(ENTITY.replace("Synthetic Example Pty Ltd", "x" * 256)),
            registry_xml(ENTITY.replace("<isCurrentIndicator>Y", "<isCurrentIndicator>N")),
            registry_xml(ENTITY, retrieval="not a datetime"),
        ):
            with self.subTest(payload=payload[:150]):
                observation = parse_observation(payload)
                self.assertEqual(observation.reason, "invalid_response")
                self.assertEqual(observation.entity_name, "")

    def test_trading_name_is_never_used_as_the_registered_entity_name(self):
        entity = ENTITY.replace("mainName", "otherEntityName")
        self.assertEqual(parse_observation(registry_xml(entity)).entity_name, "")
        self.assertEqual(parse_observation(registry_xml(ENTITY)).entity_name, "Synthetic Example Pty Ltd")


@override_settings(ABR_AUTH_GUID="synthetic-guid")
class ABRTransportTest(SimpleTestCase):
    @patch("integrations.abr.client.requests.post")
    def test_post_selects_abn_or_acn_method_without_credentials_in_the_url(self, post):
        post.return_value = SimpleNamespace(status_code=200, content=registry_xml(ENTITY))
        for abn, method, identifier in (
            ("99123456780", "SearchByABNv202001", "99123456780"),
            ("", "SearchByASICv201408", "123456780"),
        ):
            with self.subTest(method=method):
                observation = lookup_company(acn="123456780", abn=abn)
                self.assertEqual(observation.entity_status, "Active")
                post.assert_called_with(
                    f"{ABR_SERVICE}/{method}",
                    data={
                        "searchString": identifier,
                        "includeHistoricalDetails": "N",
                        "authenticationGuid": "synthetic-guid",
                    },
                    timeout=(3, 10),
                    allow_redirects=False,
                )

    @patch("integrations.abr.client.requests.post")
    def test_missing_guid_does_not_open_a_connection(self, post):
        with override_settings(ABR_AUTH_GUID=""):
            self.assertEqual(lookup_company(acn="123456780", abn="").reason, "unconfigured")
        post.assert_not_called()

    @patch("integrations.abr.client.requests.post")
    def test_timeouts_network_failures_and_http_errors_are_safe_pending_observations(self, post):
        for error, reason in (
            (requests.Timeout("synthetic-guid"), "timeout"),
            (requests.ConnectionError("synthetic-guid"), "unavailable"),
        ):
            post.side_effect = error
            observation = lookup_company(acn="123456780", abn="")
            self.assertEqual(observation.reason, reason)
            self.assertNotIn("synthetic-guid", repr(observation))
        post.side_effect = None
        for code in (301, 403, 429, 500, 503):
            post.return_value = SimpleNamespace(status_code=code, content=b"synthetic-guid")
            self.assertEqual(lookup_company(acn="123456780", abn="").reason, "provider_error")
