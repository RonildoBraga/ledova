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

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check-api-types.py"
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
        findings, _matched, _unmatched = gate.scan(self.schema(document))
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


class AnUnreachableEndpointIsAFailure(_Repository):

    def test_a_constant_the_gate_cannot_find_is_reported(self):
        self.endpoints("  THING: '/api/things/' as const,")
        self.service("export const get = (c) => c.get<Thing>(ELSEWHERE.THING);")
        self.types("export interface Thing {\n  uuid: string;\n}\n")

        with self.assertRaises(gate.Unresolvable) as caught:
            gate.service_calls()

        self.assertIn("ELSEWHERE.THING", str(caught.exception))

    def test_a_group_in_a_nested_constants_file_is_found(self):
        (self.shared / "constants/business").mkdir()
        (self.shared / "constants/business/offers.ts").write_text(
            "export const OFFER_ENDPOINTS = {\n  BASE: '/api/offers/' as const,\n}\n"
        )
        self.endpoints("  THING: '/api/things/' as const,")
        self.service("export const get = (c) => c.get<Offer>(OFFER_ENDPOINTS.BASE);")
        self.types("export interface Offer {\n  uuid: string;\n}\n")

        self.assertIn(("get", "/api/offers/"), gate.service_calls())

    def test_each_response_variant_is_checked_against_its_own_shape(self):
        self.endpoints("  PREPARE: (uuid: string) => `/api/wallets/${uuid}/prepare-transfer/`,")
        self.service("""
            export const evm = c => c.post<EvmTransfer>(ENDPOINTS.PREPARE(u), d);
            export const bitcoin = c => c.post<BitcoinTransfer>(ENDPOINTS.PREPARE(u), d);
        """)
        self.types("""
            export interface EvmTransfer {
              gasPrice: string;
              gasLimit: number;
              gasCost: string;
            }
            export interface BitcoinTransfer {
              feePerByte: string;
              feeSatoshis: number;
              feeBtc: string;
            }
        """)
        document = {
            "paths": operation("post", "/api/wallets/{uuid}/prepare-transfer/", "PreparedTransfer"),
            "components": {"schemas": {
                "PreparedTransfer": {"oneOf": [
                    {"$ref": "#/components/schemas/Evm"}, {"$ref": "#/components/schemas/Bitcoin"},
                ]},
                "Evm": {"properties": {"gasPrice": {}, "gasLimit": {}}},
                "Bitcoin": {"properties": {"feePerByte": {}, "feeSatoshis": {}}},
            }},
        }
        self.assertEqual(self.findings(document), [
            ("BitcoinTransfer", "Bitcoin", ["feebtc"]), ("EvmTransfer", "Evm", ["gascost"]),
        ])


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


class NestedFieldsStayOnTheirObject(_Repository):

    def setUp(self):
        super().setUp()
        self.endpoints("  HOLDERS: '/api/tokens/holders/',")
        self.service("export const holders = c => c.get<TokenHoldersResponse>(ENDPOINTS.HOLDERS);")
        self.declaration = """
            export interface TokenHoldersResponse {
              token: {
                uuid: string;
                name: string;
                symbol: string;
                status: string;
                totalSupply: string;
                metadata?: { label: string; };
              };
              holders: TokenHolder[];
              totalHolders: number;
            }
        """
        self.document = {
            "paths": operation("get", "/api/tokens/holders/", "ShareRegister"),
            "components": {"schemas": {"ShareRegister": {
                "properties": {"token": {}, "holders": {}, "total_holders": {}}
            }}},
        }

    def test_nested_token_fields_are_not_required_on_the_register_itself(self):
        self.types(self.declaration)
        self.assertEqual(gate.interfaces()["TokenHoldersResponse"], {
            "token": False, "holders": False, "totalholders": False,
        })
        self.assertEqual(self.findings(self.document), [])

    def test_a_required_root_field_after_a_nested_object_is_still_rejected_when_absent(self):
        self.types(self.declaration.replace("totalHolders: number;", "totalHolders: number;\n              missing: string;"))
        self.assertEqual(self.findings(self.document), [("TokenHoldersResponse", "ShareRegister", ["missing"])])

    def test_a_missing_nested_object_itself_is_still_a_missing_required_field(self):
        self.types(self.declaration)
        del self.document["components"]["schemas"]["ShareRegister"]["properties"]["token"]
        self.assertEqual(self.findings(self.document), [("TokenHoldersResponse", "ShareRegister", ["token"])])

    def test_a_quoted_brace_does_not_hide_the_next_required_field(self):
        self.types("export interface TokenHoldersResponse {\n  marker: '{';\n  missing: string;\n}\n")
        self.document["components"]["schemas"]["ShareRegister"]["properties"]["marker"] = {}
        self.assertEqual(self.findings(self.document), [("TokenHoldersResponse", "ShareRegister", ["missing"])])


class EveryServiceCallResolves(_Repository):

    def test_literal_and_computed_urls_are_rejected_including_untyped_calls(self):
        self.endpoints("  THING: '/api/things/',")
        for body in (
            "c.get<Wallet[]>('/api/wallets/')",
            'c.get<Wallet[]>("/api/wallets/")',
            "c.get<Wallet>(`/api/wallets/${uuid}/`)",
            "c.get<Wallet>(url)",
            "c.delete('/api/wallets/')",
            "c.post<T>(url, data)",
            "c.get<Wallet>(ENDPOINTS['THING'])",
            "c.get<Wallet>(ENDPOINTS.THING + '/extra/')",
            "c.get<Wallet>(ENDPOINTS.THING(uuid) + '/extra/')",
        ):
            with self.subTest(call=body):
                self.service(f"export const call = c => {body};")
                with self.assertRaises(gate.Unresolvable) as refused:
                    gate.service_calls()
                self.assertIn("thing.ts", str(refused.exception))

    def test_a_call_inside_a_url_parameter_helper_cannot_bypass_the_gate(self):
        self.service("""
            const post = <T>(c, url, data) => c.post<T>(url, data);
            export const prepare = (c, u, data) => post<PrepareTransferResponse>(c, u, data);
        """)
        with self.assertRaises(gate.Unresolvable):
            gate.service_calls()

    def test_a_generic_helper_with_a_constant_url_still_needs_a_concrete_response_shape(self):
        self.endpoints("  THING: '/api/things/',")
        self.service("const post = <T>(c, data) => c.post<T>(ENDPOINTS.THING, data);")
        document = {
            "paths": operation("post", "/api/things/", "Thing"),
            "components": {"schemas": {"Thing": {"properties": {"uuid": {}}}}},
        }
        with self.assertRaises(gate.Unresolvable) as refused:
            gate.scan(self.schema(document))
        self.assertIn("T", str(refused.exception))

    def test_quoted_examples_and_comments_are_not_calls(self):
        self.endpoints("  THING: '/api/things/',")
        self.service("""
            const example = "c.get<Wallet>('/not-a-call/')";
            const template = `c.get<Wallet>('/not-a-call/')`;
            // c.post<Wallet>('/not-a-call/')
            /* c.patch<Wallet>('/not-a-call/') */
            export const get = c => c.get<Wallet>(ENDPOINTS.THING);
        """)
        self.assertEqual(gate.service_calls(), {("get", "/api/things/"): {"Wallet"}})

    def test_a_required_wallet_field_is_checked_through_the_actual_service(self):
        constants = REPO_ROOT / "packages/shared/src/constants/api.ts"
        service = REPO_ROOT / "packages/shared/src/services/wallets.ts"
        (self.shared / "constants/api.ts").write_text(constants.read_text())
        (self.shared / "services/thing.ts").write_text(service.read_text())
        self.types("export interface Wallet {\n  uuid: string;\n  missing: string;\n}\n")
        document = {
            "paths": operation("get", "/api/wallets/", "Wallet"),
            "components": {"schemas": {"Wallet": {"properties": {"uuid": {}}}}},
        }
        self.assertEqual(self.findings(document), [("Wallet", "Wallet", ["missing"])])

    def test_every_repository_service_call_resolves_including_former_helper_types(self):
        gate.ROOT = REPO_ROOT
        gate.SHARED = REPO_ROOT / "packages/shared/src"
        calls = gate.service_calls()
        reached = set().union(*calls.values())
        for name in ("Wallet", "WalletHolding", "Transaction", "AssetSnapshot", "PortfolioSnapshot",
                     "BatchBalanceResponse", "OnRampWidgetResponse", "RequestVerificationChallengeResponse",
                     "VerifyWalletResponse", "SyncWalletResponse", "PrepareTransferResponse",
                     "PrepareBitcoinTransferResponse", "BroadcastTransferResponse"):
            with self.subTest(type=name):
                self.assertIn(name, reached)


if __name__ == "__main__":
    unittest.main()
