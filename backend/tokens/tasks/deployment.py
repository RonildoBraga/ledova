import logging
from datetime import timedelta

from django.utils import timezone
from procrastinate import RetryStrategy

from ledova_backend.procrastinate_app import app
from blockchain.models import BlockchainTransaction, TransactionStatus, TransactionType
from shared.utils.logging_utils import LoggingContext
from tokens.models import ShareIssuance, ShareToken, ShareTokenStatus
from tokens.services import ShareTokenService

logger = logging.getLogger(__name__)


@app.task(retry=RetryStrategy(max_attempts=4, wait=30))
def deploy_share_token_task(token_uuid: str):
    issuance = None
    tx_record = None

    try:
        token = ShareToken.objects.select_related("company").get(uuid=token_uuid)

        if token.status != ShareTokenStatus.DEPLOYING:
            logger.warning(f"{LoggingContext.TOKEN_DEPLOYMENT} Token {token_uuid} not deployable: {token.status}")
            return {"success": False, "error": "Token is not in deploying state"}

        company = token.company
        identifier = company.abn or company.acn

        primary_wallet = company.get_primary_wallet()
        if not primary_wallet:
            logger.error(f"{LoggingContext.TOKEN_DEPLOYMENT} No primary ETH wallet for {company.name}")
            token.status = ShareTokenStatus.DRAFT
            token.save(update_fields=["status", "updated_at"])
            return {"success": False, "error": "Company has no operator wallet or verified ETH wallet"}

        issuance = ShareIssuance.objects.create(
            token=token,
            recipient_address=primary_wallet.address,
            recipient_name=f"{company.name} Primary Wallet",
            amount=str(token.total_supply),
            issuance_type="initial",
            reason="Initial supply minted at deployment",
        )

        tx_record = BlockchainTransaction.objects.create(
            tx_type=TransactionType.TOKEN_MINT,
            status=TransactionStatus.PENDING,
            from_address="",
            to_address="",
            function_name="mint",
            function_args={
                "recipient": primary_wallet.address,
                "amount": str(token.total_supply),
                "tokenName": token.name,
                "tokenSymbol": token.symbol,
            },
            related_model="tokens.ShareIssuance",
            related_uuid=issuance.uuid,
        )

        issuance.mark_processing()
        logger.info(f"{LoggingContext.TOKEN_DEPLOYMENT} Deploying {token.symbol} for {company.name}")

        service = ShareTokenService()
        result = service.deploy_share_token(
            name=token.name,
            symbol=token.symbol,
            identifier=identifier,
            authorized_shares=int(token.total_supply),
            company_wallet_address=primary_wallet.address,
        )

        contract_address = result["contract_address"]
        mint_result = result["mint_result"]

        tx_record.to_address = contract_address
        tx_record.save(update_fields=["to_address", "updated_at"])
        tx_record.mark_submitted(mint_result["tx_hash"])

        if mint_result.get("block_number") and mint_result.get("gas_used"):
            tx_record.mark_confirmed(
                block_number=mint_result["block_number"],
                block_hash="",
                gas_used=mint_result["gas_used"],
            )

        token.mark_deployed(contract_address)

        issuance.mark_completed(
            tx_hash=mint_result["tx_hash"],
            block_number=mint_result["block_number"],
            gas_used=mint_result["gas_used"],
            transaction=tx_record,
        )

        logger.info(f"{LoggingContext.TOKEN_DEPLOYMENT} Deployed {token.symbol} at {contract_address}")

        try:
            from tokens.services import AtomicSwapService

            swap_service = AtomicSwapService()
            approval_tx = swap_service.approve_share_token(contract_address)
            if approval_tx:
                logger.info(
                    f"{LoggingContext.TOKEN_DEPLOYMENT} Auto-approved {token.symbol} for AtomicSwap - tx: {approval_tx}"
                )
        except Exception as e:
            logger.warning(
                f"{LoggingContext.TOKEN_DEPLOYMENT} Could not auto-approve {token.symbol} for AtomicSwap: {e}"
            )

        return {
            "success": True,
            "contract_address": contract_address,
            "mint_tx_hash": mint_result["tx_hash"],
        }

    except ShareToken.DoesNotExist:
        logger.error(f"{LoggingContext.TOKEN_DEPLOYMENT} Token not found: {token_uuid}")
        return {"success": False, "error": "Token not found"}

    except Exception as exc:
        logger.error(f"{LoggingContext.TOKEN_DEPLOYMENT} Deployment failed: {exc}")

        if tx_record:
            tx_record.mark_failed(str(exc))

        if issuance:
            issuance.mark_failed(str(exc))

        try:
            token = ShareToken.objects.get(uuid=token_uuid)
            token.status = ShareTokenStatus.DRAFT
            token.save(update_fields=["status", "updated_at"])
        except Exception:
            pass

        raise


@app.task
def check_pending_token_deployments():
    cutoff = timezone.now() - timedelta(minutes=10)

    pending = ShareToken.objects.filter(
        status=ShareTokenStatus.DEPLOYING,
        updated_at__lt=cutoff,
    ).select_related("company")

    service = ShareTokenService()
    checked = 0
    resolved = 0

    for token in pending:
        try:
            identifier = token.company.abn or token.company.acn
            if identifier:
                contract_address = service.get_token_by_identifier(identifier)
                if contract_address:
                    token.mark_deployed(contract_address)
                    resolved += 1
                    logger.info(f"{LoggingContext.TOKEN_DEPLOYMENT} Resolved {token.symbol} at {contract_address}")
            checked += 1
        except Exception as e:
            logger.error(f"{LoggingContext.TOKEN_DEPLOYMENT} Check failed for {token.uuid}: {e}")

    logger.info(f"{LoggingContext.TASK} Pending deployments: checked={checked}, resolved={resolved}")
    return {"checked": checked, "resolved": resolved}
