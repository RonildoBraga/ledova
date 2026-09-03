import logging
from typing import Optional

from django.conf import settings
from django.db import transaction

from blockchain.models import BlockchainTransaction, TransactionStatus, TransactionType
from integrations.base_chain.exceptions import (
    BaseChainContractError,
    BaseChainTransactionError,
)
from tokens.exceptions import (
    StablecoinBurnFailedException,
    StablecoinContractNotConfiguredException,
    StablecoinMintFailedException,
)
from tokens.services.base_token_service import BaseTokenService

logger = logging.getLogger(__name__)


class StablecoinService(BaseTokenService):

    contract_name = "AUDY"
    not_configured_exception = StablecoinContractNotConfiguredException
    mint_failed_exception = StablecoinMintFailedException
    mint_tx_type = TransactionType.STABLECOIN_MINT

    def __init__(
        self,
        contract_address: Optional[str] = None,
        signer_key: Optional[str] = None,
    ):
        super().__init__(
            contract_address=contract_address or getattr(settings, "STABLECOIN_CONTRACT_ADDRESS", None),
            signer_key=signer_key,
        )

    @transaction.atomic
    def burn(
        self,
        amount: int,
        related_model: Optional[str] = None,
        related_uuid: Optional[str] = None,
        wait_for_receipt: bool = True,
    ) -> tuple[str, Optional[BlockchainTransaction]]:
        if not self.signer_key:
            raise StablecoinContractNotConfiguredException("Blockchain operator key not configured")

        balance = self.get_balance(self.signer_address)
        if balance < amount:
            raise StablecoinBurnFailedException(
                f"Stablecoin burning failed: Insufficient balance: have {balance}, need {amount}"
            )

        tx_record = BlockchainTransaction.objects.create(
            tx_type=TransactionType.STABLECOIN_BURN,
            status=TransactionStatus.PENDING,
            from_address=self.signer_address,
            to_address=self.contract_address,
            function_name="burn",
            function_args={"amount": amount},
            related_model=related_model,
            related_uuid=related_uuid,
        )

        try:
            contract_function = self.contract.functions.burn(amount)
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

            logger.info(f"Burned {amount} AUDY from {self.signer_address} (tx={tx_hash})")
            return tx_hash, tx_record

        except (BaseChainTransactionError, BaseChainContractError) as e:
            tx_record.mark_failed(str(e))
            logger.error(f"Failed to burn AUDY: {e}")
            raise StablecoinBurnFailedException(f"Stablecoin burning failed: {e}") from e
