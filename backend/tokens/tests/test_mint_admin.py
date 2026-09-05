from datetime import date
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from tokens.admin._helpers import MintForm
from tokens.models import MintRequest, MintRequestStatus, Stablecoin, YieldToken
from tokens.services import StablecoinService, YieldTokenService, mint_service

User = get_user_model()
RECIPIENT = "0x" + "a" * 40
TX_HASH = "0x" + "ab" * 32

TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


def mint_data(amount):
    return {
        "recipient_address": RECIPIENT,
        "recipient_name": "Alice",
        "amount": amount,
        "deposit_reference": "REF-1",
        "deposit_date": "2026-09-01",
        "notes": "",
    }


class MintFormTest(TestCase):
    def test_amount_cleans_to_raw_units_for_the_token_decimals(self):
        form = MintForm(mint_data("100.00"), decimals=2, symbol="AUDY")
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["amount"], 10000)
        self.assertEqual(form.fields["amount"].label, "Amount (AUDY)")

        form = MintForm(mint_data("1.5"), decimals=6, symbol="AUSG")
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["amount"], 1500000)

        self.assertIn("amount", MintForm(mint_data("0.001"), decimals=2, symbol="AUDY").errors)
        bad_address = {**mint_data("1"), "recipient_address": "abc"}
        self.assertIn("recipient_address", MintForm(bad_address, decimals=2, symbol="AUDY").errors)


class MintServiceTest(TestCase):
    @patch("tokens.services.base_token_service.get_base_chain_client")
    def test_token_service_picks_the_service_for_the_token(self, _client):
        stablecoin = Stablecoin(symbol="AUDY", contract_address="0x" + "1" * 40)
        yield_token = YieldToken(symbol="AUSG", contract_address="0x" + "2" * 40)
        self.assertIsInstance(mint_service.token_service(stablecoin), StablecoinService)
        self.assertIsInstance(mint_service.token_service(yield_token), YieldTokenService)
        self.assertEqual(mint_service.token_service(yield_token).contract_address, yield_token.contract_address)


@override_settings(STORAGES=TEST_STORAGES)
class MintAdminTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(email="admin@example.test", password="pw-12345678")
        self.client.force_login(self.admin)
        self.stablecoin = Stablecoin.objects.create(
            name="Aussie Dollar", symbol="AUDY", contract_address="0x" + "1" * 40
        )
        self.yield_token = YieldToken.objects.create(name="Gov Bond", symbol="AUSG", contract_address="0x" + "2" * 40)
        self.service = MagicMock()
        self.service.get_total_supply.return_value = 123456
        self.service.is_minter.return_value = True
        self.service.signer_address = "0x" + "9" * 40
        self.service.mint.return_value = (TX_HASH, None)
        patcher = patch("tokens.services.mint_service.token_service", return_value=self.service)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _mint_request(self, **fields):
        return MintRequest.objects.create(
            stablecoin=self.stablecoin,
            recipient_address=RECIPIENT,
            recipient_name="Alice",
            amount=10000,
            deposit_reference="REF-1",
            deposit_date=date(2026, 9, 1),
            requested_by=self.admin,
            **fields,
        )

    def _change_url(self, mint_request):
        return reverse("admin:tokens_mintrequest_change", args=[mint_request.pk])

    def test_token_pages_render_with_mint_buttons_and_supply(self):
        for token, supply in ((self.stablecoin, "1,234.56"), (self.yield_token, "0.123456")):
            with self.subTest(token=token.symbol):
                model = token._meta.model_name
                self.assertContains(self.client.get(reverse(f"admin:tokens_{model}_changelist")), "+ Mint")
                self.assertEqual(
                    self.client.get(reverse(f"admin:tokens_{model}_change", args=[token.pk])).status_code, 200
                )
                page = self.client.get(reverse(f"admin:tokens_{model}_mint", args=[token.uuid]))
                self.assertContains(page, supply)
                self.assertContains(page, f"Amount ({token.symbol})")
        self.assertContains(self.client.get(reverse("admin:tokens_yieldtoken_changelist")), "Update NAV")

    def test_minting_from_a_token_page_creates_and_executes_a_mint_request(self):
        cases = (
            (self.stablecoin, "stablecoin", "100.00", 10000, "100.00 AUDY"),
            (self.yield_token, "yield_token", "1.5", 1500000, "1.500000 AUSG"),
        )
        for token, field, amount, raw, display in cases:
            with self.subTest(token=token.symbol):
                self.service.mint.reset_mock()
                response = self.client.post(
                    reverse(f"admin:tokens_{token._meta.model_name}_mint", args=[token.uuid]), mint_data(amount)
                )
                mint_request = MintRequest.objects.get(**{field: token})
                self.assertRedirects(response, self._change_url(mint_request), fetch_redirect_response=False)
                self.assertEqual((mint_request.amount, mint_request.status), (raw, MintRequestStatus.EXECUTED))
                self.assertEqual(mint_request.executed_by, self.admin)
                self.service.mint.assert_called_once_with(
                    to_address=RECIPIENT,
                    amount=raw,
                    related_model="tokens.MintRequest",
                    related_uuid=str(mint_request.uuid),
                )
                self.assertContains(
                    self.client.get(self._change_url(mint_request)), f"Successfully minted {display} to Alice"
                )

    def test_a_chain_failure_leaves_a_failed_request_that_can_be_retried(self):
        self.service.mint.side_effect = RuntimeError("signer is not a minter")
        self.client.post(reverse("admin:tokens_stablecoin_mint", args=[self.stablecoin.uuid]), mint_data("5.00"))
        mint_request = MintRequest.objects.get()
        self.assertEqual(
            (mint_request.status, mint_request.error_message), (MintRequestStatus.FAILED, "signer is not a minter")
        )
        change = self.client.get(self._change_url(mint_request))
        self.assertContains(change, "Minting failed: signer is not a minter")
        self.assertContains(change, reverse("admin:tokens_mintrequest_execute", args=[mint_request.uuid]))
        self.assertContains(change, "Retry")

        self.service.mint.side_effect = None
        execute_url = reverse("admin:tokens_mintrequest_execute", args=[mint_request.uuid])
        page = self.client.get(execute_url)
        self.assertContains(page, "Retry Mint Request")
        self.assertContains(page, "signer is not a minter")

        self.assertEqual(self.client.post(execute_url, {"notes": "second try"}).status_code, 200)
        mint_request.refresh_from_db()
        self.assertEqual(mint_request.status, MintRequestStatus.FAILED)

        retried = self.client.post(execute_url, {"confirm": "on", "notes": "second try"})
        self.assertRedirects(retried, self._change_url(mint_request), fetch_redirect_response=False)
        mint_request.refresh_from_db()
        self.assertEqual(mint_request.status, MintRequestStatus.EXECUTED)
        self.assertIn("Execution notes: second try", mint_request.notes)
        self.assertContains(self.client.get(self._change_url(mint_request)), "Successfully minted 5.00 AUDY to Alice")

    def test_execute_and_reject_guards_and_the_reject_flow(self):
        executed = self._mint_request(status=MintRequestStatus.EXECUTED)
        self.client.get(reverse("admin:tokens_mintrequest_execute", args=[executed.uuid]))
        self.assertContains(
            self.client.get(self._change_url(executed)), "Cannot execute: request status is &#x27;Executed&#x27;"
        )

        pending = self._mint_request()
        self.assertEqual(self.client.get(reverse("admin:tokens_mintrequest_changelist")).status_code, 200)
        self.assertContains(self.client.get(self._change_url(pending)), "Execute Mint")
        reject_url = reverse("admin:tokens_mintrequest_reject", args=[pending.uuid])
        self.assertContains(self.client.get(reject_url), "Reject Mint Request")
        rejected = self.client.post(reject_url, {"reason": "Duplicate"})
        self.assertRedirects(rejected, self._change_url(pending), fetch_redirect_response=False)
        pending.refresh_from_db()
        self.assertEqual(
            (pending.status, pending.rejection_reason, pending.executed_by), ("rejected", "Duplicate", self.admin)
        )

    def test_inactive_or_undeployed_tokens_cannot_open_the_mint_page(self):
        Stablecoin.objects.filter(pk=self.stablecoin.pk).update(is_active=False)
        response = self.client.get(reverse("admin:tokens_stablecoin_mint", args=[self.stablecoin.uuid]))
        change_url = reverse("admin:tokens_stablecoin_change", args=[self.stablecoin.pk])
        self.assertRedirects(response, change_url, fetch_redirect_response=False)
        self.assertContains(self.client.get(change_url), "Cannot mint: AUDY is not active")
        self.assertFalse(MintRequest.objects.exists())
