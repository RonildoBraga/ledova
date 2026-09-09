from typing import Optional

from django.conf import settings

from blockchain.models import TransactionType
from tokens.exceptions import (
    StablecoinContractNotConfiguredException,
    StablecoinMintFailedException,
)
from tokens.services.base_token_service import BaseTokenService


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
