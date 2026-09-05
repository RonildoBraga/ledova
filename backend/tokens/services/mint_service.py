import logging

from operators.settlement import require_deployment
from tokens.models import MintRequest
from tokens.services.stablecoin_service import StablecoinService
from tokens.services.yield_token_service import YieldTokenService

logger = logging.getLogger(__name__)


def asset_service(asset) -> StablecoinService:
    return StablecoinService(contract_address=require_deployment(asset).contract_address)


def token_service(mint_request: MintRequest):
    if mint_request.settlement_asset_id:
        return asset_service(mint_request.settlement_asset)
    return YieldTokenService(contract_address=mint_request.yield_token.contract_address)


def execute(mint_request: MintRequest, user, notes: str = ""):
    if notes:
        mint_request.notes = f"{mint_request.notes}\n\nExecution notes: {notes}"
        mint_request.save(update_fields=["notes", "updated_at"])

    try:
        tx_hash, tx_record = token_service(mint_request).mint(
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
