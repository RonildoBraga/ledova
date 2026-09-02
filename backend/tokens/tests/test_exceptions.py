from unittest.mock import Mock

from django.test import SimpleTestCase, override_settings

from integrations.base_chain.exceptions import BaseChainContractError
from tokens.exceptions import (
    ContractLoadException,
    InsufficientBalanceException,
    InvalidSignatureException,
    InvalidTokenStateException,
    NotWhitelistedException,
    OrderModificationConflictException,
    TokenDeploymentFailedException,
    TransferBroadcastException,
)
from tokens.services.share_token_service import ShareTokenService
from tokens.services.transfer_service import TransferService


class TokenExceptionTests(SimpleTestCase):
    def test_bare_classes_fall_back_to_default_detail(self):
        self.assertEqual(str(InvalidTokenStateException().detail), InvalidTokenStateException.default_detail)
        self.assertEqual(str(InvalidTokenStateException("Custom message.").detail), "Custom message.")
        self.assertEqual(InvalidTokenStateException.status_code, 400)
        self.assertEqual(OrderModificationConflictException.status_code, 409)
        self.assertEqual(InvalidSignatureException.status_code, 403)
        self.assertEqual(str(TokenDeploymentFailedException().detail), "Token deployment failed.")

    def test_not_whitelisted_message_keeps_client_matched_substring(self):
        self.assertEqual(str(NotWhitelistedException("0xabc").detail), "Address 0xabc is not whitelisted")
        self.assertEqual(str(NotWhitelistedException().detail), "Address is not whitelisted.")
        self.assertEqual(NotWhitelistedException.default_code, "not_whitelisted")

    def test_insufficient_balance_formats_amounts(self):
        exc = InsufficientBalanceException(balance=5, required=10, token_symbol="ACME")
        self.assertEqual(str(exc.detail), "Insufficient balance: you have 5 ACME but need 10")
        exc = InsufficientBalanceException(balance=150, required=2_000_000, decimals=2)
        self.assertEqual(str(exc.detail), "Insufficient balance: you have 1.50 tokens but need 20,000.00")
        self.assertEqual(str(InsufficientBalanceException().detail), "Insufficient token balance.")


class ServiceErrorMessageTests(SimpleTestCase):
    def test_broadcast_transfer_reports_invalid_hex_with_prefix(self):
        service = TransferService.__new__(TransferService)
        with self.assertRaises(TransferBroadcastException) as ctx:
            service.broadcast_transfer("0xzz")
        self.assertEqual(str(ctx.exception.detail), "Transfer broadcast failed: Invalid transaction format")

    @override_settings(SHARE_TOKEN_FACTORY_ADDRESS="0x" + "1" * 40)
    def test_factory_contract_load_failure_keeps_prefix(self):
        service = ShareTokenService.__new__(ShareTokenService)
        service._factory_contract = None
        service.chain_client = Mock()
        service.chain_client.load_contract.side_effect = BaseChainContractError("ABI missing")
        with self.assertRaises(ContractLoadException) as ctx:
            service.factory_contract
        self.assertEqual(str(ctx.exception.detail), "Failed to load contract: ABI missing")
