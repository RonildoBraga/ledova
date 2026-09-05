import logging
from collections.abc import Callable
from typing import Optional

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from web3 import Web3
from web3.logs import DISCARD

from blockchain.models import BlockchainTransaction, TransactionStatus, TransactionType
from companies.models import CompanyStatus
from integrations.base_chain import get_base_chain_client
from integrations.base_chain.exceptions import BaseChainContractError
from operators.settlement import settlement_deployments
from tokens.exceptions import (
    CompanyNotReadyException,
    ContractLoadException,
    InvalidHolderAddressException,
    InvalidRecipientAddressException,
    InvalidTokenAddressException,
    InvalidTokenStateException,
    IssuanceRefusedException,
    OperatorKeyNotConfiguredException,
    TokenBalanceRetrievalException,
    TokenDeploymentFailedException,
    TokenFactoryNotConfiguredException,
    TokenPauseFailedException,
)
from tokens.models import (
    CapitalIncreaseRequest,
    IssuanceStatus,
    RequestStatus,
    ShareIssuance,
    ShareIssuanceRequest,
    ShareToken,
    ShareTokenStatus,
)

logger = logging.getLogger(__name__)

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
NOT_WHITELISTED = "Recipient wallet is not whitelisted. Whitelist it before executing."
EXCEEDS_AUTHORIZED = "Amount exceeds authorized shares. Submit a capital increase first."
TOKEN_PAUSED = "Token is paused. Unpause it before executing."
CAP_NOT_RAISED = (
    "Authorized shares are already at or above the requested total. "
    "Resubmit the capital increase against the current cap."
)


class ShareTokenService:

    def __init__(self):
        self.chain_client = get_base_chain_client()
        self._factory_contract = None

    @property
    def factory_address(self) -> str:
        address = getattr(settings, "SHARE_TOKEN_FACTORY_ADDRESS", "")
        if not address:
            raise TokenFactoryNotConfiguredException(
                "SHARE_TOKEN_FACTORY_ADDRESS not configured. "
                "Please deploy the ShareTokenFactory contract and set the address."
            )
        return address

    @property
    def signer_key(self) -> str:
        key = getattr(settings, "BLOCKCHAIN_OPERATOR_KEY", "")
        if not key:
            raise OperatorKeyNotConfiguredException()
        return key

    @property
    def factory_contract(self):
        if self._factory_contract is None:
            try:
                self._factory_contract = self.chain_client.load_contract(
                    "ShareTokenFactory",
                    self.factory_address,
                )
            except BaseChainContractError as e:
                raise ContractLoadException(f"Failed to load contract: {e}") from e
        return self._factory_contract

    @staticmethod
    def token_identifier(token: ShareToken) -> str:
        return f"{token.company.acn}:{token.symbol}"

    @staticmethod
    def require_deployable(token: ShareToken):
        if token.status != ShareTokenStatus.DRAFT:
            raise InvalidTokenStateException(
                f"Cannot deploy token with status '{token.get_status_display()}'. Token must be in draft status."
            )
        if token.company.status != CompanyStatus.ACTIVE:
            raise CompanyNotReadyException("Company must be active before deploying tokens.")
        primary_wallet = token.company.get_primary_wallet()
        if primary_wallet is None:
            raise CompanyNotReadyException(
                "Company must have an operator wallet or verified ETH wallet before deploying tokens."
            )
        return primary_wallet

    @staticmethod
    def start_deployment(token: ShareToken) -> None:
        from tokens.tasks import deploy_share_token_task

        ShareTokenService.require_deployable(token)
        token.mark_deploying()
        deploy_share_token_task.defer(token_uuid=str(token.uuid))

    @staticmethod
    def require_retryable(token: ShareToken) -> None:
        if token.status != ShareTokenStatus.DEPLOYING:
            raise InvalidTokenStateException(
                f"Cannot retry deployment of a token with status '{token.get_status_display()}'."
            )

    @staticmethod
    def retry_deployment(token: ShareToken) -> None:
        from tokens.tasks import deploy_share_token_task

        ShareTokenService.require_retryable(token)
        deploy_share_token_task.defer(token_uuid=str(token.uuid))

    def _validate_address(self, address: str) -> str:
        if not self.chain_client.is_valid_address(address):
            raise InvalidRecipientAddressException()
        return self.chain_client.to_checksum_address(address)

    @staticmethod
    def _tx_result(tx_hash: str, receipt: dict | None) -> dict:
        return {
            "tx_hash": tx_hash,
            "block_number": receipt["blockNumber"] if receipt else None,
            "gas_used": receipt["gasUsed"] if receipt else None,
        }

    def _mint_to(
        self, contract_address: str, recipient: str, amount: int, on_sent: Callable[[str], None] | None = None
    ) -> dict:
        token_contract = self.load_share_token(contract_address)
        recipient_checksum = self.chain_client.to_checksum_address(recipient)

        mint_fn = token_contract.functions.mint(recipient_checksum, amount)
        tx_hash, _ = self.chain_client.send_transaction(mint_fn, self.signer_key, wait_for_receipt=False)
        if on_sent is not None:
            on_sent(tx_hash)
        receipt = self.chain_client.wait_for_receipt(tx_hash)

        return self._tx_result(tx_hash, receipt)

    def _get_balance(self, contract_name: str, contract_address: str, holder: str) -> int:
        if not self.chain_client.is_valid_address(holder):
            raise InvalidHolderAddressException()

        contract = self.chain_client.load_contract(
            contract_name, self.chain_client.to_checksum_address(contract_address)
        )
        holder_checksum = self.chain_client.to_checksum_address(holder)

        return contract.functions.balanceOf(holder_checksum).call()

    def load_share_token(self, contract_address: str):
        if not self.chain_client.is_valid_address(contract_address):
            raise InvalidTokenAddressException()

        checksum = self.chain_client.to_checksum_address(contract_address)
        return self.chain_client.load_contract("ShareToken", checksum)

    def deploy_token(self, token: ShareToken) -> dict:
        identifier = self.token_identifier(token)
        try:
            contract_address = self.get_token_by_identifier(identifier)
        except Exception as exc:
            logger.error(f"getTokenByIdentifier({identifier}) failed: {exc}")
            self._abandon_unless_sent(token)
            raise TokenDeploymentFailedException(f"Token deployment failed: {exc}") from exc
        if contract_address:
            logger.info(f"Adopting {token.symbol} already created at {contract_address} for {identifier}")
            self._warn_on_cap_mismatch(token, contract_address)
            adopted = True
        else:
            adopted = False
            contract_address = self._resume_share_token(token, identifier) if token.deployment_tx_hash else None
            if contract_address is None:
                contract_address = self._create_share_token(token, identifier)

        token.mark_deployed(contract_address)
        self._approve_for_swap(token)
        return {"contract_address": contract_address, "identifier": identifier, "adopted": adopted}

    def resolve_pending_deployment(self, token: ShareToken) -> Optional[str]:
        contract_address = self.get_token_by_identifier(self.token_identifier(token))
        if contract_address:
            self._warn_on_cap_mismatch(token, contract_address)
            self._confirm_deployment_transaction(token)
            token.mark_deployed(contract_address)
            self._approve_for_swap(token)
        return contract_address

    def _confirm_deployment_transaction(self, token: ShareToken) -> None:
        tx_record = token.deployment_transaction
        if tx_record is None or tx_record.status == TransactionStatus.CONFIRMED:
            return
        try:
            receipt = self.chain_client.get_transaction_receipt(token.deployment_tx_hash)
        except Exception as exc:
            logger.warning(f"Could not read the receipt of {token.deployment_tx_hash} for {token.symbol}: {exc}")
            return
        if receipt is not None and receipt["status"] == 1:
            self._confirm_record(tx_record, receipt)

    @staticmethod
    def _confirm_record(tx_record: BlockchainTransaction, receipt) -> None:
        tx_record.mark_confirmed(
            block_number=receipt["blockNumber"],
            block_hash=Web3.to_hex(receipt["blockHash"]),
            gas_used=receipt["gasUsed"],
        )

    @staticmethod
    def _abandon_unless_sent(token: ShareToken) -> None:
        if not token.mark_draft_unless_sent():
            logger.warning(f"{token.symbol} stays deploying: create transaction {token.deployment_tx_hash} was sent")

    def _warn_on_cap_mismatch(self, token: ShareToken, contract_address: str) -> None:
        try:
            authorized, _ = self.share_supply(contract_address)
        except Exception as exc:
            logger.warning(f"Could not read authorizedShares of {token.symbol} at {contract_address}: {exc}")
            return
        if authorized != int(token.total_supply):
            logger.warning(
                f"{token.symbol} at {contract_address} authorises {authorized} shares on chain "
                f"but {token.total_supply} in the database"
            )

    def _created_address(self, tx_hash: str, receipt) -> str:
        events = self.factory_contract.events.ShareTokenCreated().process_receipt(receipt, errors=DISCARD)
        if not events:
            raise TokenDeploymentFailedException(f"No ShareTokenCreated event in receipt {tx_hash}")
        return events[0]["args"]["tokenAddress"]

    def _resume_share_token(self, token: ShareToken, identifier: str) -> Optional[str]:
        tx_hash = token.deployment_tx_hash
        tx_record = token.deployment_transaction
        try:
            receipt = self.chain_client.get_transaction_receipt(tx_hash)
            if receipt is not None and receipt["status"] != 1:
                logger.warning(f"createShareToken({identifier}) {tx_hash} reverted; a fresh create is safe")
                if tx_record:
                    tx_record.mark_reverted(f"Transaction reverted: {tx_hash}")
                token.discard_deployment_transaction()
                return None
            if receipt is None:
                receipt = self.chain_client.wait_for_receipt(tx_hash)
            contract_address = self._created_address(tx_hash, receipt)
        except Exception as exc:
            logger.error(f"createShareToken({identifier}) {tx_hash} still unconfirmed, token stays deploying: {exc}")
            if tx_record:
                tx_record.mark_failed(str(exc))
            raise TokenDeploymentFailedException(f"Token deployment unconfirmed: {exc}") from exc

        if tx_record:
            self._confirm_record(tx_record, receipt)
        logger.info(f"ShareToken {token.symbol} created at {contract_address} by resumed {tx_hash}")
        return contract_address

    def _create_share_token(self, token: ShareToken, identifier: str) -> str:
        issuer_wallet = token.company.get_primary_wallet()
        if issuer_wallet is None:
            self._abandon_unless_sent(token)
            raise CompanyNotReadyException("Company has no operator wallet or verified ETH wallet")

        authorized_shares = int(token.total_supply)
        tx_record = None
        try:
            signer_address = self.chain_client.get_address_from_private_key(self.signer_key)
            tx_record = BlockchainTransaction.objects.create(
                tx_type=TransactionType.SHARE_TOKEN_DEPLOY,
                status=TransactionStatus.PENDING,
                from_address=signer_address,
                to_address=self.factory_address,
                function_name="createShareToken",
                function_args={
                    "name": token.name,
                    "symbol": token.symbol,
                    "identifier": identifier,
                    "authorizedShares": str(authorized_shares),
                    "tokenOwner": signer_address,
                    "issuerWallet": issuer_wallet.address,
                },
                related_model="tokens.ShareToken",
                related_uuid=token.uuid,
            )
            create_fn = self.factory_contract.functions.createShareToken(
                token.name, token.symbol, identifier, authorized_shares, signer_address
            )
            tx_hash, _ = self.chain_client.send_transaction(create_fn, self.signer_key, wait_for_receipt=False)
        except Exception as exc:
            logger.error(f"createShareToken({identifier}) not sent: {exc}")
            if tx_record:
                tx_record.mark_failed(str(exc))
            self._abandon_unless_sent(token)
            raise TokenDeploymentFailedException(f"Token deployment failed: {exc}") from exc

        tx_record.mark_submitted(tx_hash)
        if not token.bind_deployment_transaction(tx_hash, tx_record):
            logger.warning(
                f"createShareToken({identifier}) {tx_hash} sent while {token.deployment_tx_hash} was already "
                f"recorded by another worker; the one that confirms is kept"
            )
        logger.info(f"createShareToken({identifier}) sent: {tx_hash}")

        try:
            receipt = self.chain_client.wait_for_receipt(tx_hash)
            contract_address = self._created_address(tx_hash, receipt)
        except Exception as exc:
            logger.error(f"createShareToken({identifier}) unconfirmed, token stays deploying: {exc}")
            tx_record.mark_failed(str(exc))
            raise TokenDeploymentFailedException(f"Token deployment unconfirmed: {exc}") from exc

        self._confirm_record(tx_record, receipt)
        if token.deployment_tx_hash != tx_hash:
            logger.warning(f"{token.symbol} was created by {tx_hash}, not by the recorded {token.deployment_tx_hash}")
            token.mark_deploying(tx_hash=tx_hash, transaction=tx_record)
        logger.info(f"ShareToken {token.symbol} created at {contract_address}")
        return contract_address

    @staticmethod
    def _approve_for_swap(token: ShareToken) -> None:
        from tokens.services import AtomicSwapService

        try:
            approval_tx = AtomicSwapService().approve_share_token(token.contract_address)
            if approval_tx:
                logger.info(f"Approved {token.symbol} for AtomicSwap: {approval_tx}")
        except Exception as exc:
            logger.warning(f"Could not approve {token.symbol} for AtomicSwap: {exc}")

    def get_token_by_identifier(self, identifier: str) -> Optional[str]:
        address = self.factory_contract.functions.getTokenByIdentifier(identifier).call()
        return None if address == ZERO_ADDRESS else address

    def create_issuance_request(
        self, token, recipient: str, amount: int, user, reason: str = "", issuance_type: str = "additional"
    ) -> ShareIssuanceRequest:
        if token.status != "deployed":
            raise InvalidTokenStateException("Only deployed tokens can issue shares.")

        if not token.contract_address:
            raise InvalidTokenStateException("Token has no contract address.")

        if not recipient or not Web3.is_address(recipient):
            raise InvalidRecipientAddressException()

        if amount <= 0:
            raise ValidationError({"amount": "Amount must be a positive integer."})

        issuance_request = ShareIssuanceRequest.objects.create(
            token=token,
            recipient_address=recipient,
            amount=amount,
            issuance_type=issuance_type,
            reason=reason,
            submitted_by=user,
            submitted_at=timezone.now(),
        )

        issuance_request.dilution_percentage = issuance_request.calculate_dilution()
        issuance_request.save(update_fields=["dilution_percentage", "updated_at"])

        logger.info(f"User {user.email} created issuance request: {amount} {token.symbol} to {recipient}")

        return issuance_request

    def share_supply(self, contract_address: str) -> tuple[int, int]:
        token_contract = self.load_share_token(contract_address)
        return token_contract.functions.authorizedShares().call(), token_contract.functions.totalSupply().call()

    def is_recipient_whitelisted(self, address: str) -> bool:
        from whitelist.services import WhitelistService

        return WhitelistService().is_whitelisted(address)

    def execute_request(self, request, executed_by=None) -> dict:
        token = request.token
        if not request.can_be_executed:
            raise InvalidTokenStateException(f"Cannot execute request with status '{request.get_status_display()}'")
        if not token.contract_address or token.status not in (ShareTokenStatus.DEPLOYED, ShareTokenStatus.PAUSED):
            request.mark_failed("Token is not deployed on blockchain")
            raise InvalidTokenStateException("Token is not deployed on blockchain")

        if isinstance(request, CapitalIncreaseRequest):
            return self._execute_capital_increase(request)
        return self._execute_issuance(request, executed_by)

    @staticmethod
    def issuance_key(request: ShareIssuanceRequest) -> str:
        return f"issuance-request:{request.uuid}"

    @staticmethod
    def _start_execution(request) -> None:
        try:
            request.mark_executing()
        except ValueError as exc:
            raise InvalidTokenStateException(str(exc)) from exc

    def _refuse_if_paused(self, request: ShareIssuanceRequest) -> None:
        token = request.token
        if token.status == ShareTokenStatus.PAUSED or self.read_paused(token):
            request.mark_refused(TOKEN_PAUSED)
            raise IssuanceRefusedException(TOKEN_PAUSED)

    def _execute_issuance(self, request: ShareIssuanceRequest, executed_by) -> dict:
        token = request.token
        recipient = self._validate_address(request.recipient_address)
        issuance = ShareIssuance.objects.filter(idempotency_key=self.issuance_key(request)).first()
        if issuance is not None and issuance.tx_hash:
            result = self._resume_issuance(request, issuance)
            if result is not None:
                return result

        self._refuse_if_paused(request)
        if not self.is_recipient_whitelisted(recipient):
            request.mark_refused(NOT_WHITELISTED)
            raise IssuanceRefusedException(NOT_WHITELISTED)
        authorized, issued = self.share_supply(token.contract_address)
        if request.amount > authorized - issued:
            request.mark_refused(EXCEEDS_AUTHORIZED)
            raise IssuanceRefusedException(EXCEEDS_AUTHORIZED)

        self._start_execution(request)
        if issuance is None:
            issuance = ShareIssuance.objects.create(
                token=token,
                recipient_address=recipient,
                recipient_name=request.recipient_name,
                amount=str(request.amount),
                issuance_type=request.issuance_type,
                reason=f"Issuance request: {request.reason}",
                initiated_by=executed_by or request.reviewed_by,
                idempotency_key=self.issuance_key(request),
            )
        issuance.mark_processing()
        logger.info(f"Minting {request.amount} {token.symbol} to {recipient}")

        try:
            result = self._mint_to(
                token.contract_address,
                recipient,
                request.amount,
                on_sent=lambda tx_hash: issuance.mark_processing(tx_hash=tx_hash),
            )
        except Exception as exc:
            logger.error(f"Issuance failed: {exc}")
            issuance.mark_failed(str(exc))
            request.mark_failed(str(exc))
            raise

        self._complete_issuance(request, issuance, result)
        return result

    def _resume_issuance(self, request: ShareIssuanceRequest, issuance: ShareIssuance) -> Optional[dict]:
        tx_hash = issuance.tx_hash
        if issuance.status == IssuanceStatus.COMPLETED:
            logger.info(f"mint {tx_hash} for request {request.uuid} already completed; nothing to send or wait on")
            request.refresh_from_db(fields=["status", "executed_issuance", "executed_at"])
            if request.status != RequestStatus.EXECUTED:
                request.mark_executed(issuance)
            return {"tx_hash": tx_hash, "block_number": issuance.block_number, "gas_used": issuance.gas_used}
        try:
            receipt = self.chain_client.get_transaction_receipt(tx_hash)
            if receipt is not None and receipt["status"] != 1:
                logger.warning(f"mint {tx_hash} for request {request.uuid} reverted; a fresh mint is safe")
                issuance.mark_reverted(f"Transaction reverted: {tx_hash}")
                return None
            if receipt is None:
                receipt = self.chain_client.wait_for_receipt(tx_hash)
        except Exception as exc:
            logger.error(f"mint {tx_hash} for request {request.uuid} still unconfirmed: {exc}")
            issuance.mark_failed(str(exc))
            request.mark_failed(str(exc))
            raise

        logger.info(f"mint {tx_hash} for request {request.uuid} already mined; completing without sending")
        result = self._tx_result(tx_hash, receipt)
        self._complete_issuance(request, issuance, result)
        return result

    @staticmethod
    def _complete_issuance(request: ShareIssuanceRequest, issuance: ShareIssuance, result: dict) -> None:
        issuance.mark_completed(
            tx_hash=result["tx_hash"], block_number=result["block_number"], gas_used=result["gas_used"]
        )
        request.mark_executed(issuance)
        logger.info(f"Issuance executed for {request.token.symbol}: {result['tx_hash']}")

    def resolve_executing_issuance(self, request: ShareIssuanceRequest) -> Optional[str]:
        issuance = (
            ShareIssuance.objects.filter(idempotency_key=self.issuance_key(request))
            .exclude(tx_hash__isnull=True)
            .exclude(tx_hash="")
            .first()
        )
        if issuance is None:
            logger.warning(f"Request {request.uuid} is executing with no mint recorded; left for the operator")
            return None
        tx_hash = issuance.tx_hash
        receipt = self.chain_client.get_transaction_receipt(tx_hash)
        if receipt is None:
            return None
        if receipt["status"] != 1:
            logger.warning(f"mint {tx_hash} for request {request.uuid} reverted; the request can be retried")
            issuance.mark_reverted(f"Transaction reverted: {tx_hash}")
            request.mark_failed(f"Transaction reverted: {tx_hash}")
            return "reverted"
        logger.info(f"mint {tx_hash} for request {request.uuid} mined while the worker was gone; completing")
        self._complete_issuance(request, issuance, self._tx_result(tx_hash, receipt))
        return "executed"

    def _execute_capital_increase(self, request: CapitalIncreaseRequest) -> dict:
        token = request.token
        refused = False
        failure = None
        result = None
        with transaction.atomic():
            ShareToken.objects.select_for_update().get(pk=token.pk)
            request.refresh_from_db(fields=["status"])
            if not request.can_be_executed:
                raise InvalidTokenStateException(f"Cannot execute request with status '{request.get_status_display()}'")
            tx_record = self._recorded_increase(request)
            if tx_record is not None:
                try:
                    result = self._resume_capital_increase(request, tx_record)
                except InvalidTokenStateException:
                    raise
                except Exception as exc:
                    failure = exc
            if failure is None and result is None:
                authorized, _ = self.share_supply(token.contract_address)
                token.refresh_from_db(fields=["total_supply"])
                if authorized == request.new_authorized_total and int(token.total_supply) < authorized:

                    logger.warning(
                        f"{token.symbol} authorized shares are already {authorized} on chain with the DB cap at "
                        f"{token.total_supply}; adopting the chain cap for request {request.uuid} without sending"
                    )
                    result = {
                        "tx_hash": None,
                        "block_number": None,
                        "gas_used": None,
                        "new_authorized_total": request.new_authorized_total,
                        "adopted": True,
                    }
                refused = result is None and request.new_authorized_total <= authorized
                if refused:
                    request.mark_refused(CAP_NOT_RAISED)
                elif result is None:
                    self._start_execution(request)
                    logger.info(
                        f"Raising {token.symbol} authorized shares from {authorized} to {request.new_authorized_total}"
                    )
                    try:
                        result = self.increase_authorized_shares(request)
                    except Exception as exc:
                        failure = exc
            if failure is not None:
                request.mark_failed(str(failure))
            elif result is not None:
                self._complete_capital_increase(request, result)

        if refused:
            raise IssuanceRefusedException(CAP_NOT_RAISED)
        if failure is not None:
            logger.error(f"Capital increase failed: {failure}")
            raise failure
        return result

    @staticmethod
    def _recorded_increase(request: CapitalIncreaseRequest) -> Optional[BlockchainTransaction]:
        return (
            BlockchainTransaction.objects.filter(
                related_model=CapitalIncreaseRequest._meta.label,
                related_uuid=request.uuid,
                function_name="setAuthorizedShares",
                status__in=(TransactionStatus.SUBMITTED, TransactionStatus.FAILED, TransactionStatus.CONFIRMED),
            )
            .exclude(tx_hash__isnull=True)
            .exclude(tx_hash="")
            .order_by("-created_at")
            .first()
        )

    def _resume_capital_increase(
        self, request: CapitalIncreaseRequest, tx_record: BlockchainTransaction
    ) -> Optional[dict]:
        tx_hash = tx_record.tx_hash
        try:
            receipt = self.chain_client.get_transaction_receipt(tx_hash)
            if receipt is not None and receipt["status"] != 1:
                logger.warning(
                    f"setAuthorizedShares {tx_hash} for request {request.uuid} reverted; a fresh call is safe"
                )
                tx_record.mark_reverted(f"Transaction reverted: {tx_hash}")
                return None
            if receipt is None:
                self._start_execution(request)
                receipt = self.chain_client.wait_for_receipt(tx_hash)
        except InvalidTokenStateException:
            raise
        except Exception as exc:
            logger.error(f"setAuthorizedShares {tx_hash} for request {request.uuid} still unconfirmed: {exc}")
            tx_record.mark_failed(str(exc))
            raise TokenDeploymentFailedException(f"Capital increase unconfirmed: {exc}") from exc

        self._confirm_record(tx_record, receipt)
        logger.info(
            f"setAuthorizedShares {tx_hash} for request {request.uuid} already mined; completing without sending"
        )
        return {**self._tx_result(tx_hash, receipt), "new_authorized_total": request.new_authorized_total}

    @staticmethod
    def _complete_capital_increase(request: CapitalIncreaseRequest, result: dict) -> None:
        token = request.token
        token.refresh_from_db(fields=["total_supply"])
        token.total_supply = str(max(int(token.total_supply), request.new_authorized_total))
        token.save(update_fields=["total_supply", "updated_at"])
        request.mark_executed()
        logger.info(f"Capital increase executed for {token.symbol}: {result['tx_hash'] or 'adopted from chain'}")

    def resolve_executing_capital_increase(self, request: CapitalIncreaseRequest) -> Optional[str]:
        tx_record = self._recorded_increase(request)
        if tx_record is None:
            logger.warning(
                f"Request {request.uuid} is executing with no setAuthorizedShares recorded; left for the operator"
            )
            return None
        tx_hash = tx_record.tx_hash
        receipt = self.chain_client.get_transaction_receipt(tx_hash)
        if receipt is None:
            return None
        if receipt["status"] != 1:
            logger.warning(
                f"setAuthorizedShares {tx_hash} for request {request.uuid} reverted; the request can be retried"
            )
            tx_record.mark_reverted(f"Transaction reverted: {tx_hash}")
            request.mark_failed(f"Transaction reverted: {tx_hash}")
            return "reverted"
        logger.info(
            f"setAuthorizedShares {tx_hash} for request {request.uuid} mined while the worker was gone; completing"
        )
        result = {**self._tx_result(tx_hash, receipt), "new_authorized_total": request.new_authorized_total}
        with transaction.atomic():
            ShareToken.objects.select_for_update().get(pk=request.token.pk)
            request.refresh_from_db(fields=["status"])
            if request.status == RequestStatus.EXECUTED:
                logger.info(f"Request {request.uuid} was completed by another worker while the sweep read the chain")
                return None
            self._confirm_record(tx_record, receipt)
            self._complete_capital_increase(request, result)
        return "executed"

    def increase_authorized_shares(self, request: CapitalIncreaseRequest) -> dict:
        token = request.token
        new_authorized_total = request.new_authorized_total
        tx_record = None
        try:
            signer_address = self.chain_client.get_address_from_private_key(self.signer_key)
            tx_record = BlockchainTransaction.objects.create(
                tx_type=TransactionType.OTHER,
                status=TransactionStatus.PENDING,
                from_address=signer_address,
                to_address=token.contract_address,
                function_name="setAuthorizedShares",
                function_args={"newAuthorizedShares": str(new_authorized_total)},
                related_model=CapitalIncreaseRequest._meta.label,
                related_uuid=request.uuid,
            )
            token_contract = self.load_share_token(token.contract_address)
            set_auth_fn = token_contract.functions.setAuthorizedShares(new_authorized_total)
            tx_hash, _ = self.chain_client.send_transaction(set_auth_fn, self.signer_key, wait_for_receipt=False)
        except Exception as exc:
            logger.error(f"setAuthorizedShares({new_authorized_total}) not sent: {exc}")
            if tx_record:
                tx_record.mark_failed(str(exc))
            raise TokenDeploymentFailedException(f"Capital increase failed: {exc}") from exc

        tx_record.mark_submitted(tx_hash)
        logger.info(f"setAuthorizedShares({new_authorized_total}) sent for {token.symbol}: {tx_hash}")
        try:
            receipt = self.chain_client.wait_for_receipt(tx_hash)
        except Exception as exc:
            logger.error(f"setAuthorizedShares({new_authorized_total}) {tx_hash} unconfirmed: {exc}")
            tx_record.mark_failed(str(exc))
            raise TokenDeploymentFailedException(f"Capital increase unconfirmed: {exc}") from exc

        self._confirm_record(tx_record, receipt)
        return {**self._tx_result(tx_hash, receipt), "new_authorized_total": new_authorized_total}

    @staticmethod
    def require_pausable(token: ShareToken, paused: bool) -> None:
        if paused and token.status != ShareTokenStatus.DEPLOYED:
            raise InvalidTokenStateException("Only deployed tokens can be paused.")
        if not paused and token.status not in (ShareTokenStatus.PAUSED, ShareTokenStatus.DEPLOYED):
            raise InvalidTokenStateException("Only paused tokens can be unpaused.")

    def pause(self, token: ShareToken) -> None:
        self.require_pausable(token, True)
        self._set_paused(token, True)

    def unpause(self, token: ShareToken) -> None:
        self.require_pausable(token, False)
        if token.status == ShareTokenStatus.PAUSED or self.read_paused(token):
            self._set_paused(token, False)
            return
        raise InvalidTokenStateException("Only paused tokens can be unpaused.")

    def read_paused(self, token: ShareToken) -> bool:
        try:
            return self.load_share_token(token.contract_address).functions.paused().call()
        except Exception as exc:
            logger.error(f"paused() could not be read for {token.symbol}: {exc}")
            raise TokenPauseFailedException(f"Token paused state could not be read: {exc}") from exc

    def _set_paused(self, token: ShareToken, paused: bool) -> None:
        function_name = "pause" if paused else "unpause"
        if self.read_paused(token) == paused:
            logger.warning(f"{token.symbol} is already {function_name}d on chain; reconciling the database status")
        else:
            try:
                contract_function = getattr(self.load_share_token(token.contract_address).functions, function_name)()
                tx_hash, _ = self.chain_client.send_transaction(
                    contract_function, self.signer_key, wait_for_receipt=True
                )
                logger.info(f"{function_name}() confirmed for {token.symbol}: {tx_hash}")
            except Exception as exc:
                logger.error(f"{function_name}() failed for {token.symbol}: {exc}")
                if not self._paused_state_is(token, paused):
                    raise TokenPauseFailedException(f"Token {function_name} failed: {exc}") from exc
                logger.warning(f"{function_name}() for {token.symbol} failed after the call mined; reconciling")
        if paused:
            token.mark_paused()
        else:
            token.mark_unpaused()

    def _paused_state_is(self, token: ShareToken, paused: bool) -> bool:
        try:
            return self.read_paused(token) == paused
        except TokenPauseFailedException:
            return False

    def get_token_balance(self, contract_address: str, holder: str) -> int:
        try:
            return self._get_balance("ShareToken", contract_address, holder)
        except InvalidHolderAddressException:
            raise
        except Exception as e:
            logger.error(f"Error getting balance: {e}")
            raise TokenBalanceRetrievalException() from e

    def get_token_holders(self, token) -> list[dict]:
        holders_data = []

        if token.status == "deployed" and token.contract_address:
            try:
                issuances_qs = ShareIssuance.objects.filter_by_token(token)
                address_names = issuances_qs.unique_holders_with_names()

                for address in address_names.keys():
                    try:
                        balance = self.get_token_balance(token.contract_address, address)
                        if balance > 0:
                            holders_data.append(
                                {
                                    "address": address,
                                    "name": address_names.get(address) or None,
                                    "balance": str(balance),
                                    "source": "blockchain",
                                }
                            )
                    except Exception as e:
                        logger.warning(f"Failed to get balance for {address}: {e}")

            except Exception as e:
                logger.error(f"Failed to query blockchain for holders: {e}")
                holders_data = ShareIssuance.objects.filter_by_token(token).holders_as_list()
        else:
            holders_data = ShareIssuance.objects.filter_by_token(token).holders_as_list()

        total_supply = sum(int(h["balance"]) for h in holders_data) if holders_data else 0
        for holder in holders_data:
            balance = int(holder["balance"])
            holder["percentage"] = round((balance / total_supply * 100), 2) if total_supply > 0 else 0

        holders_data.sort(key=lambda x: int(x["balance"]), reverse=True)

        return holders_data

    def get_wallet_token_balances(self, wallet_address: str) -> dict:
        wallet_checksum = self._validate_address(wallet_address)

        balances = []

        tokens = ShareToken.objects.deployed_with_contract()
        for token in tokens:
            try:
                balance = self.get_token_balance(token.contract_address, wallet_checksum)
                if balance > 0:
                    balances.append(
                        {
                            "token": str(token.uuid),
                            "symbol": token.symbol,
                            "name": token.name,
                            "balance": str(balance),
                            "contractAddress": token.contract_address,
                            "decimals": 0,
                            "type": "share_token",
                        }
                    )
            except Exception as e:
                logger.warning(f"Failed to get balance for {token.symbol}: {e}")

        for deployment in settlement_deployments():
            asset = deployment.asset
            try:
                balance = self._get_balance("AUDY", deployment.contract_address, wallet_checksum)
                if balance > 0:
                    balances.append(
                        {
                            "token": str(asset.uuid),
                            "symbol": asset.symbol,
                            "name": asset.name,
                            "balance": str(balance),
                            "contractAddress": deployment.contract_address,
                            "decimals": deployment.decimals,
                            "type": "stablecoin",
                        }
                    )
            except Exception as e:
                logger.warning(f"Failed to get settlement asset balance for {asset.symbol}: {e}")

        return {"walletAddress": wallet_checksum, "balances": balances}
