"""The one execute-mint flow behind the stablecoin, yield-token and mint-request admin pages."""

import logging

from tokens.models import MintRequest, Stablecoin
from tokens.services.stablecoin_service import StablecoinService
from tokens.services.yield_token_service import YieldTokenService

logger = logging.getLogger(__name__)


def token_service(token):
    """StablecoinService or YieldTokenService bound to the token's contract."""
    service_class = StablecoinService if isinstance(token, Stablecoin) else YieldTokenService
    return service_class(contract_address=token.contract_address)


def execute(mint_request: MintRequest, user, notes: str = ""):
    """Mint on-chain for the request and record the outcome on it; a failure is stored, then re-raised."""
    if notes:
        mint_request.notes = f"{mint_request.notes}\n\nExecution notes: {notes}"
        mint_request.save(update_fields=["notes", "updated_at"])

    try:
        tx_hash, tx_record = token_service(mint_request.token).mint(
            to_address=mint_request.recipient_address,
            amount=mint_request.amount,
            related_model="tokens.MintRequest",
            related_uuid=str(mint_request.uuid),
        )
    except Exception as exc:
        mint_request.mark_failed(str(exc))
        logger.exception(f"Mint execution failed for {mint_request.uuid}: {exc}")
        raise

    mint_request.mark_executed(user=user, transaction=tx_record)
    return tx_hash, tx_record
