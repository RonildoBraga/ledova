import copy
import json
from contextlib import ExitStack
from datetime import timedelta
from io import StringIO
from unittest.mock import patch
from uuid import uuid4

from django.contrib import admin
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, connection
from django.forms import modelform_factory
from django.test import SimpleTestCase, TransactionTestCase, override_settings
from django.utils import timezone
from web3 import Web3

from blockchain.models import (
    BlockchainTransaction,
    OutgoingCutoverHold,
    OutgoingHistoryCapture,
    OutgoingHistoryEvidence,
    OutgoingOperation,
    SignedAttempt,
    SigningAccount,
    TransactionType,
)
from blockchain.services.outgoing_inventory import (
    COVERAGE_LIMITS,
    InventorySnapshot,
    OutgoingInventoryError,
    _analyze,
    collect_inventory,
    record_inventory,
    report_inventory,
)
from blockchain.tests.outgoing_fixtures import claim_operation, sign_claim
from blockchain.tests.outgoing_inventory_fixtures import (
    CONTRACT,
    RECIPIENT,
    observed_identity,
    signed_source,
    snapshot,
)
from integrations.base_chain.client import BaseChainClient
from shared.db import atomic
from shared.tests.tenants import make_tenant
from tokens.models import (
    MintRequest,
    NAVUpdate,
    ShareIssuance,
    ShareIssuanceRequest,
    ShareToken,
    YieldToken,
)

PRIVATE_MODELS = (OutgoingHistoryCapture, OutgoingHistoryEvidence, OutgoingCutoverHold)


class OutgoingInventoryDecodeTest(SimpleTestCase):
    def evidence(self, source):
        return _analyze(snapshot(source))[0]

    @override_settings(BLOCKCHAIN_CHAIN_ID=84532, BLOCKCHAIN_OPERATOR_KEY="0x" + "22" * 32)
    def test_staged_303_payload_separates_raw_terms_source_link_and_missing_authority(self):
        row = self.evidence(signed_source())
        self.assertTrue(row.raw_valid)
        self.assertTrue(row.terms_match)
        self.assertTrue(row.source_link_valid)
        self.assertEqual((row.observed_chain_id, row.observed_sender, row.observed_nonce), observed_identity())
        self.assertEqual(row.findings, ["missing_chain_provenance", "missing_signer_authorization"])
        self.assertNotIn("expected_chain_id", row.expected_terms)
        self.assertNotIn("authorized_sender", row.expected_terms)

    def test_wrong_target_value_selector_recipient_amount_or_noncanonical_calldata_fails_terms(self):
        good = signed_source()["journal_entry"]["raw_transaction"]
        data = "0x40c10f19" + RECIPIENT[2:].rjust(64, "0") + f"{10:064x}"
        for changed in (
            {"to": Web3.to_checksum_address(RECIPIENT)},
            {"value": 1},
            {"data": "0xffffffff" + data[10:]},
            {"data": "0x40c10f19" + CONTRACT[2:].rjust(64, "0") + f"{10:064x}"},
            {"data": data[:-1] + "b"},
            {"data": data + "00"},
        ):
            with self.subTest(changed=changed):
                source = signed_source(transaction_changes=changed)
                self.assertNotEqual(source["journal_entry"]["raw_transaction"], good)
                row = self.evidence(source)
                self.assertTrue(row.raw_valid)
                self.assertTrue(row.source_link_valid)
                self.assertFalse(row.terms_match)
                self.assertIn("mint_terms_mismatch", row.findings)

    def test_mismatched_missing_and_ambiguous_request_link_cannot_bind_an_operation(self):
        for mode in ("key", "amount", "recipient", "token", "reverse_link", "ambiguous", "missing", "capital"):
            with self.subTest(mode=mode):
                source = signed_source()
                request = source["request_candidates"][0]
                if mode == "key":
                    source["row"]["idempotency_key"] = "unrelated"
                elif mode == "amount":
                    request["amount"] += 1
                elif mode == "recipient":
                    request["recipient_address"] = CONTRACT
                elif mode == "token":
                    request["token_id"] = str(uuid4())
                elif mode == "reverse_link":
                    request["executed_issuance_id"] = str(uuid4())
                elif mode == "ambiguous":
                    source["request_candidates"].append(copy.deepcopy(request))
                elif mode == "missing":
                    source["request_candidates"] = []
                else:
                    source["capital_links"] = [str(uuid4())]
                row = self.evidence(source)
                self.assertTrue(row.raw_valid)
                self.assertFalse(row.source_link_valid)
                self.assertEqual(row.operation_key, "")
                self.assertIn("invalid_source_link", row.findings)

    def test_malformed_unsupported_and_misidentified_payloads_are_retained(self):
        for value, code in (
            ("0xnot-hex-private", "malformed_raw_payload"),
            ("0x02ff", "unsupported_envelope"),
            ("0xc001", "invalid_signature"),
            (None, "missing_raw_payload"),
        ):
            with self.subTest(code=code):
                source = signed_source()
                source["journal_entry"]["raw_transaction"] = value
                source["journal_entry"]["tx_hash"] = None
                row = self.evidence(source)
                self.assertFalse(row.raw_valid)
                self.assertIn(code, row.findings)
                if code in ("unsupported_envelope", "invalid_signature"):
                    self.assertEqual(bytes(row.raw_transaction), bytes.fromhex(value[2:]))
                else:
                    self.assertEqual(row.source_snapshot["journal_entry"]["raw_transaction"], value)
        source = signed_source()
        source["journal_entry"]["tx_hash"] = "0x" + "00" * 32
        row = self.evidence(source)
        self.assertTrue(row.raw_valid)
        self.assertIn("recorded_hash_mismatch", row.findings)

    def test_large_nonce_is_preserved_and_never_truncated_to_the_allocator_range(self):
        row = self.evidence(signed_source(transaction_changes={"nonce": 2**80}))
        self.assertTrue(row.raw_valid)
        self.assertEqual(row.observed_nonce, str(2**80))
        self.assertIn("unsupported_integer_range", row.findings)

    def test_only_the_exact_linked_unsigned_marker_proves_an_unsigned_attempt(self):
        for abandoned in (False, True):
            source = signed_source()
            source["journal_entry"] = {"id": source["journal_entry"]["id"]}
            if abandoned:
                source["journal_entry"]["abandoned"] = True
            source["entry_keys"] = sorted(source["journal_entry"])
            source["row"]["tx_hash"] = None
            row = self.evidence(source)
            self.assertTrue(row.proved_unsigned)
            self.assertIsNone(row.observed_sender)
            self.assertIsNone(row.raw_transaction)
            self.assertEqual(row.findings, [] if abandoned else ["unsigned_inflight_snapshot"])
            source["entry_keys"].append("unexpected")
            self.assertFalse(self.evidence(source).proved_unsigned)


class OutgoingInventoryRecordingTest(TransactionTestCase):
    def record(self, *sources):
        return record_inventory(snapshot(*sources), uuid4())

    def test_same_nonce_conflicts_and_duplicate_hash_bindings_preserve_every_raw_variant(self):
        first, different, same_hash_other_request = signed_source(), signed_source(1, amount=11), signed_source(2)
        self.record(first)
        report = self.record(different, same_hash_other_request)
        rows = list(OutgoingHistoryEvidence.objects.order_by("source_uuid"))
        self.assertEqual(len(rows), 3)
        self.assertEqual(
            [Web3.to_hex(row.raw_transaction) for row in rows],
            [source["journal_entry"]["raw_transaction"] for source in (first, different, same_hash_other_request)],
        )
        self.assertGreater(report["hold_reasons"]["nonce_payload_conflict"], 0)
        self.assertGreater(report["hold_reasons"]["hash_operation_conflict"], 0)
        for hold in OutgoingCutoverHold.objects.filter(
            reason__in=("nonce_payload_conflict", "hash_operation_conflict")
        ):
            self.assertEqual(len(hold.evidence_refs), 2)
            self.assertEqual(hold.scope, "signer")
        self.assertFalse(OutgoingOperation.objects.exists())
        self.assertFalse(SigningAccount.objects.exists())
        self.assertFalse(SignedAttempt.objects.exists())

    def test_same_capture_reentry_ignores_capture_clock_and_changed_source_refuses(self):
        capture_id = uuid4()
        first = snapshot(signed_source(), signed_source(1, amount=11))
        report = record_inventory(first, capture_id)
        counts = [model.objects.count() for model in PRIVATE_MODELS]
        later = InventorySnapshot(first.snapshot_at + timedelta(days=2), tuple(reversed(first.sources)))
        self.assertEqual(record_inventory(later, capture_id), report)
        self.assertEqual([model.objects.count() for model in PRIVATE_MODELS], counts)
        changed = copy.deepcopy(first.sources[0])
        changed["row"]["amount"] = "12"
        with self.assertRaisesMessage(OutgoingInventoryError, "different source manifest"):
            record_inventory(snapshot(changed, first.sources[1]), capture_id)
        self.assertEqual([model.objects.count() for model in PRIVATE_MODELS], counts)

    def test_source_reassignment_appends_a_conflict_without_rewriting_old_evidence(self):
        first = signed_source()
        self.record(first)
        changed = signed_source(amount=11)
        report = self.record(changed)
        self.assertEqual(report["hold_reasons"]["source_identity_conflict"], 1)
        self.assertEqual(OutgoingHistoryEvidence.objects.count(), 2)
        self.assertEqual(
            OutgoingHistoryEvidence.objects.order_by("created_at").first().source_snapshot["row"]["amount"], "10"
        )

    def test_terminal_legacy_status_and_missing_identity_never_authorize_release(self):
        for status in ("failed", "confirmed", "reverted", "pending", "submitted"):
            for tx_hash in (None, "0x" + "ab" * 32):
                BlockchainTransaction.objects.create(
                    tx_type=TransactionType.STABLECOIN_BURN, status=status, from_address=RECIPIENT, tx_hash=tx_hash
                )
                scanned = collect_inventory()
                report = record_inventory(scanned, uuid4())
                self.assertFalse(report["cutover_authorized"])
                self.assertEqual(report["raw_valid_count"], 0)
                self.assertEqual(report["evidence_count"], BlockchainTransaction.objects.count())
                if tx_hash:
                    BlockchainTransaction.objects.filter(tx_hash=tx_hash).update(tx_hash=None)
        holds = set(OutgoingCutoverHold.objects.values_list("uuid", flat=True))
        empty = InventorySnapshot(timezone.now(), ())
        clean = record_inventory(empty, uuid4())
        self.assertTrue(holds.issubset(set(OutgoingCutoverHold.objects.values_list("uuid", flat=True))))
        self.assertEqual(set(clean["hold_reasons"]), set(COVERAGE_LIMITS))
        self.assertFalse(clean["cutover_authorized"])

    @override_settings(BLOCKCHAIN_CHAIN_ID=31337, BLOCKCHAIN_OPERATOR_KEY="0x" + "22" * 32)
    def test_unknown_historical_signer_stays_unassigned_with_a_deployment_hold(self):
        BlockchainTransaction.objects.create(tx_type=TransactionType.STABLECOIN_MINT, from_address=RECIPIENT, nonce=7)
        report = record_inventory(collect_inventory(), uuid4())
        evidence = OutgoingHistoryEvidence.objects.get()
        self.assertIsNone(evidence.observed_sender)
        self.assertIsNone(evidence.observed_chain_id)
        self.assertIsNone(evidence.observed_nonce)
        self.assertEqual(evidence.source_snapshot["row"]["from_address"], RECIPIENT)
        self.assertTrue(
            OutgoingCutoverHold.objects.filter(scope="deployment", reason="missing_signer_authorization").exists()
        )
        self.assertFalse(SigningAccount.objects.exists())
        self.assertFalse(report["cutover_authorized"])

    def test_refuses_app_alias_wrapping_atomic_and_manual_autocommit_disablement(self):
        source = snapshot()
        calls = (collect_inventory, lambda: report_inventory(source), lambda: record_inventory(source, uuid4()))
        for call in calls:
            with self.subTest(call=call):
                with atomic(), self.assertRaisesMessage(OutgoingInventoryError, "outside every transaction"):
                    call()
                connection.set_autocommit(False)
                try:
                    with self.assertRaisesMessage(OutgoingInventoryError, "outside every transaction"):
                        call()
                finally:
                    connection.set_autocommit(True)
                with patch("blockchain.services.outgoing_inventory.current_alias", return_value="app"):
                    with self.assertRaisesMessage(OutgoingInventoryError, "operator connection"):
                        call()
        self.assertEqual(record_inventory(source, uuid4())["evidence_count"], 1)

    def test_private_models_cannot_be_edited_or_exposed_in_admin_forms_reports_or_errors(self):
        source = snapshot()
        report = record_inventory(source, uuid4())
        raw = source.sources[0]["journal_entry"]["raw_transaction"]
        self.assertNotIn(raw, json.dumps(report))
        for model in PRIVATE_MODELS:
            row = model.objects.first()
            self.assertNotIn(raw, repr(row))
            self.assertEqual(modelform_factory(model, fields="__all__")().fields, {})
            self.assertNotIn(model, admin.site._registry)
            with self.assertRaises(ValueError):
                row.save()
            with self.assertRaises(ValueError):
                row.delete()
            with self.assertRaises(ValueError):
                model.objects.update(updated_at=timezone.now())
            with self.assertRaises(ValueError):
                model.objects.all().delete()
        self.assertNotIn(raw, repr(source))
        with patch.object(OutgoingHistoryEvidence.objects, "bulk_create", side_effect=DatabaseError(raw)):
            with self.assertRaises(OutgoingInventoryError) as caught:
                record_inventory(source, uuid4())
        self.assertNotIn(raw, str(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)
        self.assertEqual(OutgoingHistoryCapture.objects.count(), 1)

    def test_command_is_read_only_by_default_and_only_explicit_recording_creates_private_rows(self):
        source, output = snapshot(), StringIO()
        command = "blockchain.management.commands.inventory_outgoing_history"
        with patch(f"{command}.collect_inventory", return_value=source):
            call_command("inventory_outgoing_history", stdout=output)
            self.assertEqual([model.objects.count() for model in PRIVATE_MODELS], [0, 0, 0])
            self.assertFalse(json.loads(output.getvalue())["cutover_authorized"])
            output.seek(0)
            output.truncate()
            call_command("inventory_outgoing_history", record=True, capture_id=uuid4(), stdout=output)
            self.assertEqual(OutgoingHistoryCapture.objects.count(), 1)
            self.assertEqual(OutgoingHistoryEvidence.objects.count(), 1)
            self.assertNotIn(source.sources[0]["journal_entry"]["raw_transaction"], output.getvalue())
            for options in ({"record": True}, {"capture_id": uuid4()}):
                with self.assertRaises(CommandError):
                    call_command("inventory_outgoing_history", **options, stdout=output)
            with atomic(), self.assertRaises(CommandError):
                call_command("inventory_outgoing_history", stdout=output)


class OutgoingInventorySourceTest(TransactionTestCase):
    def setUp(self):
        self.tenant = make_tenant("inventory")
        ShareToken.objects.filter(pk=self.tenant.deployed_token.pk).update(contract_address=CONTRACT)
        self.request = ShareIssuanceRequest.objects.create(
            token=self.tenant.deployed_token,
            recipient_address=RECIPIENT,
            amount=10,
            reason="Synthetic inventory",
            status="failed",
        )
        self.source = signed_source()
        self.issuance = ShareIssuance.objects.create(
            token=self.tenant.deployed_token,
            recipient_address=RECIPIENT,
            recipient_name="private-source-name",
            recipient_residential_address="private-source-residential-address",
            amount="10",
            status="failed",
            tx_hash=self.source["row"]["tx_hash"],
            mint_journal=[self.source["journal_entry"]],
            idempotency_key=f"issuance-request:{self.request.pk}",
        )

    def test_read_only_inventory_and_recording_never_sign_broadcast_or_mutate_authoritative_state(self):
        sign_claim(claim_operation())
        models = (
            ShareIssuance,
            ShareIssuanceRequest,
            BlockchainTransaction,
            SigningAccount,
            SignedAttempt,
            OutgoingOperation,
        )
        before = [list(model.objects.order_by("uuid").values()) for model in models]
        with ExitStack() as stack:
            for method in (
                "get_nonce",
                "assert_expected_chain",
                "get_transaction_receipt",
                "send_raw_transaction",
                "send_transaction",
                "sign_transaction",
            ):
                stack.enter_context(
                    patch.object(BaseChainClient, method, side_effect=AssertionError("inventory must stay local"))
                )
            for path in (
                "eth_account.Account.sign_transaction",
                "tokens.services.mint_journal.release_unsigned_mint",
                "blockchain.services.outgoing.sign_operation",
                "blockchain.services.outgoing.record_receipt",
            ):
                stack.enter_context(patch(path, side_effect=AssertionError("inventory must stay inert")))
            captured = collect_inventory()
            report = report_inventory(captured)
            self.assertEqual([model.objects.count() for model in PRIVATE_MODELS], [0, 0, 0])
            stored = record_inventory(captured, uuid4())
        self.assertEqual(stored["manifest_digest"], report["manifest_digest"])
        self.assertEqual([list(model.objects.order_by("uuid").values()) for model in models], before)
        row = OutgoingHistoryEvidence.objects.get(source_uuid=self.issuance.pk)
        self.assertTrue(row.raw_valid and row.terms_match and row.source_link_valid)
        self.assertEqual(row.operation_key, f"issuance-request:{self.request.pk}")
        serialized = json.dumps(row.source_snapshot)
        self.assertNotIn("private-source-name", serialized)
        self.assertNotIn("private-source-residential-address", serialized)
        self.assertNotIn(self.source["journal_entry"]["raw_transaction"], serialized)

    def test_collector_retains_all_journal_slots_invalid_ids_and_legacy_hashless_rows(self):
        entry = self.source["journal_entry"]
        self.issuance.mint_journal = [entry, {**entry, "reverted": True}, "malformed-entry", {"id": "invalid"}]
        self.issuance.save(update_fields=["mint_journal"])
        legacy = ShareIssuance.objects.create(
            token=self.tenant.deployed_token,
            recipient_address=RECIPIENT,
            amount="1",
            status="failed",
            mint_journal=None,
        )
        record_inventory(collect_inventory(), uuid4())
        rows = list(OutgoingHistoryEvidence.objects.filter(source_uuid=self.issuance.pk).order_by("entry_key"))
        self.assertEqual(len(rows), 4)
        self.assertEqual([Web3.to_hex(row.raw_transaction) for row in rows[:2]], [entry["raw_transaction"]] * 2)
        self.assertIn("invalid_attempt_identity", rows[0].findings)
        self.assertIn("malformed_journal", rows[2].findings)
        self.assertIn("missing_raw_payload", OutgoingHistoryEvidence.objects.get(source_uuid=legacy.pk).findings)

    def test_fixed_registry_captures_domain_rows_and_confirms_only_existing_projection_links(self):
        yielding = YieldToken.objects.create(
            name="Synthetic inventory yield", symbol="INVY", contract_address=RECIPIENT
        )
        mint = MintRequest.objects.create(
            yield_token=yielding,
            recipient_address=RECIPIENT,
            recipient_name="private-mint-name",
            amount=10,
            status="failed",
            deposit_reference="synthetic",
            deposit_date="2026-09-01",
            requested_by=self.tenant.user,
        )
        nav = NAVUpdate.objects.create(
            yield_token=yielding,
            old_nav_per_token="1",
            new_nav_per_token="2",
            total_reserve_value="200",
            updated_by=self.tenant.user,
            notes="private-nav-note",
        )
        transaction = BlockchainTransaction.objects.create(
            tx_type=TransactionType.OTHER,
            from_address=RECIPIENT,
            function_name="setAuthorizedShares",
            function_args={"newAuthorizedShares": "100", "private_note": "omit-this-note"},
            related_model="tokens.CapitalIncreaseRequest",
            related_uuid=self.tenant.capital_increase.pk,
        )
        dangling = BlockchainTransaction.objects.create(
            tx_type=TransactionType.TOKEN_MINT,
            from_address=RECIPIENT,
            related_model="authentication.User",
            related_uuid=uuid4(),
        )
        sources = collect_inventory().sources
        labels = {source["model"] for source in sources}
        self.assertTrue(
            {
                "tokens.ShareToken",
                "tokens.CapitalIncreaseRequest",
                "tokens.SwapOrder",
                "tokens.ShareIssuance",
                "blockchain.BlockchainTransaction",
                "tokens.MintRequest",
                "tokens.NAVUpdate",
            }.issubset(labels)
        )
        linked = next(source for source in sources if source["uuid"] == str(transaction.pk))
        self.assertEqual(linked["related"]["uuid"], str(self.tenant.capital_increase.pk))
        self.assertNotIn("omit-this-note", json.dumps(linked))
        unlinked = next(source for source in sources if source["uuid"] == str(dangling.pk))
        self.assertIsNone(unlinked["related"])
        mint_source = next(source for source in sources if source["uuid"] == str(mint.pk))
        nav_source = next(source for source in sources if source["uuid"] == str(nav.pk))
        self.assertFalse(mint_source["projection_exists"])
        self.assertFalse(nav_source["projection_exists"])
        self.assertEqual(nav_source["yield_token"]["uuid"], str(yielding.pk))
        self.assertNotIn("private-mint-name", json.dumps(mint_source))
        self.assertNotIn("private-nav-note", json.dumps(nav_source))

    def test_a_failed_share_request_without_an_issuance_is_an_unresolved_source(self):
        unlinked = ShareIssuanceRequest.objects.create(
            token=self.tenant.deployed_token,
            recipient_address=RECIPIENT,
            amount=1,
            reason="Synthetic lost projection",
            status="failed",
        )
        record_inventory(collect_inventory(), uuid4())
        evidence = OutgoingHistoryEvidence.objects.get(source_uuid=unlinked.pk)
        self.assertEqual(evidence.source_model, "tokens.ShareIssuanceRequest")
        self.assertIn("missing_raw_payload", evidence.findings)
        self.assertFalse(evidence.proved_unsigned)
        self.assertIsNone(evidence.observed_sender)
        self.assertFalse(
            OutgoingHistoryEvidence.objects.filter(
                source_model="tokens.ShareIssuanceRequest", source_uuid=self.request.pk
            ).exists()
        )
