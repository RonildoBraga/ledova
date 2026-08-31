import logging
from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.db import transaction

from blockchain.models import BlockchainTransaction, TransactionStatus
from integrations.base_chain import get_base_chain_client
from integrations.base_chain.exceptions import (
    BaseChainContractError,
    BaseChainTransactionError,
)
from integrations.blockchain.factory import get_blockchain_client
from shared.constants import EVM_BLOCKCHAINS
from tokens.exceptions import (
    InvalidRecipientAddressException,
    NotAuthorizedMinterException,
)

logger = logging.getLogger(__name__)


class BaseTokenService:

    contract_name: str = ""
    not_configured_exception: type[Exception] = Exception
    mint_failed_exception: type[Exception] = Exception
    mint_tx_type: str = ""

    def __init__(
        self,
        contract_address: Optional[str] = None,
        signer_key: Optional[str] = None,
    ):
        self.chain_client = get_base_chain_client()
        self.contract_address = contract_address
        self.signer_key = signer_key or getattr(settings, "BLOCKCHAIN_OPERATOR_KEY", None)
        self._contract = None

    @property
    def contract(self):
        if self._contract is None:
            if not self.contract_address:
                raise self.not_configured_exception(f"{self.contract_name} contract address not configured.")
            self._contract = self.chain_client.load_contract(self.contract_name, self.contract_address)
        return self._contract

    @property
    def signer_address(self) -> str:
        if not self.signer_key:
            raise self.not_configured_exception(
                "Blockchain operator key not configured. Set BLOCKCHAIN_OPERATOR_KEY in environment."
            )
        account = self.chain_client.account_from_key(self.signer_key)
        return account.address

    def is_minter(self, address: str) -> bool:
        checksum_address = self.chain_client.to_checksum_address(address)
        return self.contract.functions.minters(checksum_address).call()

    def get_balance(self, address: str) -> int:
        checksum_address = self.chain_client.to_checksum_address(address)
        return self.contract.functions.balanceOf(checksum_address).call()

    def get_total_supply(self) -> int:
        return self.contract.functions.totalSupply().call()

    def get_decimals(self) -> int:
        return self.contract.functions.decimals().call()

    @transaction.atomic
    def mint(
        self,
        to_address: str,
        amount: int,
        related_model: Optional[str] = None,
        related_uuid: Optional[str] = None,
        wait_for_receipt: bool = True,
    ) -> tuple[str, Optional[BlockchainTransaction]]:
        if not self.signer_key:
            raise self.not_configured_exception("Blockchain operator key not configured")

        if not self.chain_client.is_valid_address(to_address):
            raise InvalidRecipientAddressException()

        checksum_address = self.chain_client.to_checksum_address(to_address)

        if not self.is_minter(self.signer_address):
            raise NotAuthorizedMinterException(self.signer_address)

        tx_record = BlockchainTransaction.objects.create(
            tx_type=self.mint_tx_type,
            status=TransactionStatus.PENDING,
            from_address=self.signer_address,
            to_address=self.contract_address,
            function_name="mint",
            function_args={"to": checksum_address, "amount": amount},
            related_model=related_model,
            related_uuid=related_uuid,
        )

        try:
            contract_function = self.contract.functions.mint(checksum_address, amount)
            tx_hash, receipt = self.chain_client.send_transaction(
                contract_function,
                self.signer_key,
                wait_for_receipt=wait_for_receipt,
            )

            tx_record.mark_submitted(tx_hash)
            if receipt:
                tx_record.mark_confirmed(
                    block_number=receipt["blockNumber"],
                    block_hash=receipt["blockHash"].hex(),
                    gas_used=receipt["gasUsed"],
                )

            return tx_hash, tx_record

        except (BaseChainTransactionError, BaseChainContractError) as e:
            tx_record.mark_failed(str(e))
            raise self.mint_failed_exception(str(e)) from e

    def _send_and_confirm(
        self,
        contract_function,
        tx_type: str,
        function_name: str,
        function_args: dict,
        related_model: Optional[str] = None,
        related_uuid: Optional[str] = None,
        wait_for_receipt: bool = True,
    ) -> tuple[str, BlockchainTransaction]:
        tx_record = BlockchainTransaction.objects.create(
            tx_type=tx_type,
            status=TransactionStatus.PENDING,
            from_address=self.signer_address,
            to_address=self.contract_address,
            function_name=function_name,
            function_args=function_args,
            related_model=related_model,
            related_uuid=related_uuid,
        )

        tx_hash, receipt = self.chain_client.send_transaction(
            contract_function,
            self.signer_key,
            wait_for_receipt=wait_for_receipt,
        )

        tx_record.mark_submitted(tx_hash)
        if receipt:
            tx_record.mark_confirmed(
                block_number=receipt["blockNumber"],
                block_hash=receipt["blockHash"].hex(),
                gas_used=receipt["gasUsed"],
            )

        return tx_hash, tx_record


def get_multi_chain_supply(symbol: str) -> tuple[Decimal | None, list[dict]]:
    from assets.models import Asset

    asset = Asset.objects.filter(symbol=symbol).first()
    if not asset:
        return None, []

    deployments = asset.chain_deployments.filter(is_active=True, chain__in=EVM_BLOCKCHAINS)
    if not deployments.exists():
        return None, []

    total = Decimal("0")
    any_success = False
    chain_data = []

    for deployment in deployments:
        entry = {
            "chain": deployment.chain,
            "contract_address": deployment.contract_address,
            "decimals": deployment.decimals,
            "supply": None,
        }
        try:
            client = get_blockchain_client(deployment.chain)
            supply = client.get_total_supply(deployment.contract_address, deployment.decimals)
            total += supply
            any_success = True
            entry["supply"] = str(supply)
        except Exception:
            logger.warning(f"Failed to fetch supply for {symbol} on {deployment.chain}")
        chain_data.append(entry)

    return (total if any_success else None), chain_data
