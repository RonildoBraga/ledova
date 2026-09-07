from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APITestCase

from assets.models import Asset, AssetChainDeployment
from feature_flags.models import FeatureFlag
from integrations.base_chain.exceptions import BaseChainConnectionError
from operators.models import Operator
from shared.tests.tenants import make_tenant
from tokens.exceptions import WalletBalancesUnavailableException
from tokens.services.share_token_service import ShareTokenService

BALANCES = "/api/v1/trading/wallets/balances/"


class BalancesRefuseRatherThanGuessTest(APITestCase):

    def setUp(self):
        FeatureFlag.objects.update_or_create(name="trading_enabled", defaults={"enabled": True})
        self.tenant = make_tenant("balances")
        self.client.force_authenticate(self.tenant.user)

    def _get(self):
        return self.client.get(BALANCES, {"wallet_address": self.tenant.wallet.address})

    @patch("tokens.views.trading_wallet.ShareTokenService")
    def test_a_cold_client_that_cannot_connect_refuses_rather_than_erroring(self, service_class):
        service_class.side_effect = BaseChainConnectionError("Failed to connect to configured EVM endpoint")

        response = self._get()

        self.assertEqual(response.status_code, 503)
        self.assertIn("could not be reached", response.json()["detail"])

    @patch("tokens.views.trading_wallet.ShareTokenService")
    def test_a_warm_client_that_cannot_read_refuses_rather_than_answering_nothing(self, service_class):
        service_class.return_value.get_wallet_token_balances.side_effect = WalletBalancesUnavailableException(
            "The balance of QAT could not be read: boom"
        )

        response = self._get()

        self.assertEqual(response.status_code, 503)
        self.assertIn("QAT", response.json()["detail"])

    @patch("tokens.views.trading_wallet.ShareTokenService")
    def test_a_readable_chain_still_answers_two_hundred(self, service_class):
        service_class.return_value.get_wallet_token_balances.return_value = {"balances": []}

        self.assertEqual(self._get().status_code, 200)


class TheServiceRefusesAPartialAnswerTest(TestCase):

    def setUp(self):
        self.tenant = make_tenant("partial")
        self.service = ShareTokenService.__new__(ShareTokenService)

    def _stablecoin(self):
        operator = Operator.get()
        asset = Asset.objects.create(
            symbol="AUDZ", name="AUD Yield Probe", asset_type="stablecoin", decimals=2, is_active=True
        )
        AssetChainDeployment.objects.create(
            asset=asset,
            chain=operator.receiving_wallet_chain,
            contract_address="0x" + "9b" * 20,
            decimals=2,
            is_active=True,
        )
        operator.supported_settlement_assets.add(asset)
        return asset

    def test_one_unreadable_share_class_refuses_the_whole_answer(self):
        with (
            patch.object(ShareTokenService, "_validate_address", side_effect=lambda address: address),
            patch.object(ShareTokenService, "get_token_balance", side_effect=RuntimeError("node said no")),
            self.assertRaises(WalletBalancesUnavailableException) as raised,
        ):
            self.service.get_wallet_token_balances(self.tenant.wallet.address)

        self.assertIn("could not be read", str(raised.exception.detail))
        self.assertNotIn("node said no", str(raised.exception.detail))

    def test_the_operator_still_gets_what_the_caller_no_longer_does(self):
        with (
            patch.object(ShareTokenService, "_validate_address", side_effect=lambda address: address),
            patch.object(ShareTokenService, "get_token_balance", side_effect=RuntimeError("node said no")),
            self.assertLogs("tokens.services.share_token_service", level="ERROR") as logged,
            self.assertRaises(WalletBalancesUnavailableException),
        ):
            self.service.get_wallet_token_balances(self.tenant.wallet.address)

        self.assertIn("node said no", " ".join(logged.output))

    def test_an_unreadable_settlement_asset_refuses_too(self):
        self._stablecoin()
        with (
            patch.object(ShareTokenService, "_validate_address", side_effect=lambda address: address),
            patch.object(ShareTokenService, "get_token_balance", return_value=0),
            patch.object(ShareTokenService, "_get_balance", side_effect=RuntimeError("node said no")),
            self.assertRaises(WalletBalancesUnavailableException) as raised,
        ):
            self.service.get_wallet_token_balances(self.tenant.wallet.address)

        self.assertIn("AUDZ", str(raised.exception.detail))
