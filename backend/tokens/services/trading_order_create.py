from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import connections
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError
from web3 import Web3

from shared.db import atomic, current_alias
from tokens.exceptions import (
    ChallengeMismatchException,
    CreateOrderInsufficientBalanceException,
    CreateOrderNotWhitelistedException,
    OrderSubmissionConflictException,
)
from tokens.models import (
    OrderSubmission,
    OrderSubmissionStatus,
    ShareToken,
    TransferOrder,
    TransferOrderType,
)
from tokens.services.signing_challenge import spend
from tokens.services.token_transfer_service import TokenTransferService
from tokens.services.trading_order_service import TradingOrderService
from wallets.constants import WALLET_VERIFICATION_STATUS_VERIFIED
from wallets.models import Wallet
from wallets.models.wallet import Blockchain

NOT_FOUND = "Order submission not found."
BUSINESS_REFUSALS = {
    CreateOrderNotWhitelistedException: "not_whitelisted",
    CreateOrderInsufficientBalanceException: "insufficient_balance",
}


@dataclass(frozen=True)
class SubmissionResult:
    submission: OrderSubmission
    created: bool = False
    challenge: dict | None = None


def _independent_boundary():
    connection = connections[current_alias()]
    if not connection.get_autocommit() or connection.in_atomic_block:
        raise ImproperlyConfigured("Order submissions require autocommit outside every transaction block.")


def _find_submission(actor, account_id, submission_id):
    return (
        OrderSubmission.objects.visible_to_user(actor)
        .select_for_update(of=("self",))
        .filter(owner_account_id=account_id, submission_id=submission_id)
        .first()
    )


def _assert_original_terms(submission, data):
    expected = (
        submission.owner_account_id,
        submission.wallet_id,
        submission.token_id,
        submission.wallet_address,
        submission.order_type,
        submission.quantity,
        submission.min_quantity,
        submission.price_per_share,
    )
    actual = (
        data["owner_account_uuid"],
        data["wallet_uuid"],
        data["token"],
        data["wallet_address"],
        data["order_type"],
        data["quantity"],
        data["min_quantity"],
        data["price_per_share"],
    )
    if actual != expected:
        raise OrderSubmissionConflictException()


def _lock_authorized_wallet(actor, submission):
    wallet = Wallet.objects.select_for_update(of=("self",)).filter(pk=submission.wallet_id).first()
    if wallet is None or wallet.user_account_id != submission.owner_account_id:
        raise NotFound(NOT_FOUND)
    membership = wallet.user_account.user_profiles.through
    if not (
        actor is not None
        and actor.is_authenticated
        and membership.objects.select_for_update(of=("self",))
        .filter(useraccount_id=submission.owner_account_id, userprofile__user=actor)
        .exists()
    ):
        raise NotFound(NOT_FOUND)
    if not Web3.is_address(wallet.address) or Web3.to_checksum_address(wallet.address) != submission.wallet_address:
        raise NotFound(NOT_FOUND)
    return wallet


def _eligible_token(token_id, wallet):
    if wallet.verification_status != WALLET_VERIFICATION_STATUS_VERIFIED or wallet.chain not in (
        Blockchain.ETHEREUM.value,
        Blockchain.BASE.value,
    ):
        raise ValidationError({"wallet_uuid": "Select a verified EVM wallet from one of your accounts."})
    token = ShareToken.objects.filter(pk=token_id).first()
    if token is None:
        raise ValidationError({"token": "Token not found"})
    if not token.is_deployed:
        raise ValidationError({"token": "Token is not deployed"})
    return token


def _pending_token(submission, wallet):
    token = _eligible_token(submission.token_id, wallet)
    if submission.chain_id != settings.BLOCKCHAIN_CHAIN_ID:
        raise ChallengeMismatchException("chain")
    if token.contract_address.lower() != submission.verifying_contract.lower():
        raise ChallengeMismatchException("contract")
    return token


def _recover_order(submission, actor):
    if submission.order_id is not None:
        order = TransferOrder.objects.visible_to_user(actor).filter(pk=submission.order_id).first()
        if order is None or (order.wallet_id, order.owner_account_id, order.token_id, order.wallet_address) != (
            submission.wallet_id,
            submission.owner_account_id,
            submission.token_id,
            submission.wallet_address,
        ):
            raise NotFound(NOT_FOUND)
        submission.order = order


def issue_order_submission(actor, data):
    _independent_boundary()
    with atomic(durable=True):
        submission = _find_submission(actor, data["owner_account_uuid"], data["submission_id"])
        if submission is None:
            token = _eligible_token(data["token"], data["wallet"])
            submission, _ = OrderSubmission.objects.get_or_create(
                owner_account_id=data["owner_account_uuid"],
                submission_id=data["submission_id"],
                defaults={
                    "wallet_id": data["wallet_uuid"],
                    "token": token,
                    "initiated_by": actor,
                    "wallet_address": data["wallet_address"],
                    "order_type": data["order_type"],
                    "quantity": data["quantity"],
                    "min_quantity": data["min_quantity"],
                    "price_per_share": data["price_per_share"],
                    "chain_id": settings.BLOCKCHAIN_CHAIN_ID,
                    "verifying_contract": token.contract_address,
                    "token_metadata": {"name": token.name, "symbol": token.symbol},
                },
            )
            submission = OrderSubmission.objects.select_for_update(of=("self",)).get(pk=submission.pk)
        _assert_original_terms(submission, data)
        wallet = _lock_authorized_wallet(actor, submission)
        if submission.status != OrderSubmissionStatus.PENDING:
            _recover_order(submission, actor)
            return SubmissionResult(submission)
        token = _pending_token(submission, wallet)
        challenge = TradingOrderService.get_order_create_message(
            token=token,
            wallet_address=submission.wallet_address,
            order_type=submission.order_type,
            quantity=submission.quantity,
            min_quantity=submission.min_quantity,
            price_per_share=submission.price_per_share,
            wallet=wallet,
            submission=submission,
        )
        return SubmissionResult(submission, challenge=challenge)


def execute_order_submission(actor, data):
    _independent_boundary()
    with atomic(durable=True):
        submission = _find_submission(actor, data["owner_account_uuid"], data["submission_id"])
        if submission is None:
            raise NotFound(NOT_FOUND)
        _assert_original_terms(submission, data)
        wallet = _lock_authorized_wallet(actor, submission)
        if submission.status != OrderSubmissionStatus.PENDING:
            _recover_order(submission, actor)
            return SubmissionResult(submission)
        token = _pending_token(submission, wallet)
        challenge = TradingOrderService.verify_order_create_signature(
            wallet_address=submission.wallet_address,
            token_uuid=str(submission.token_id),
            order_type=submission.order_type,
            quantity=submission.quantity,
            min_quantity=submission.min_quantity,
            price_per_share=submission.price_per_share,
            digest=data.get("digest"),
            signature=data.get("signature"),
            submission=submission,
        )
        spend(challenge, data["signature"])
        try:
            with atomic():
                order, match = TokenTransferService().create_order_and_match(
                    token=token,
                    order_type=submission.order_type,
                    actor=actor,
                    wallet=wallet,
                    owner_account=wallet.user_account,
                    wallet_address=submission.wallet_address,
                    quantity=submission.quantity,
                    min_quantity=submission.min_quantity,
                    price_per_share=submission.price_per_share,
                )
        except tuple(BUSINESS_REFUSALS) as exc:
            if type(exc) not in BUSINESS_REFUSALS:
                raise
            submission.status = OrderSubmissionStatus.REFUSED
            submission.refusal_code = BUSINESS_REFUSALS[type(exc)]
            submission.refusal_detail = str(exc.detail)
        else:
            submission.status = OrderSubmissionStatus.CREATED
            submission.order = order
            if match is not None:
                submission.initial_counter_order = match[
                    "buy_order" if submission.order_type == TransferOrderType.SELL else "sell_order"
                ]
                submission.initial_swap = match["swap_order"]
        submission.executed_challenge = challenge
        submission.resolved_at = timezone.now()
        submission.save(
            update_fields=[
                "status",
                "order",
                "initial_counter_order",
                "initial_swap",
                "refusal_code",
                "refusal_detail",
                "executed_challenge",
                "resolved_at",
                "updated_at",
            ]
        )
        _recover_order(submission, actor)
        return SubmissionResult(submission, created=submission.status == OrderSubmissionStatus.CREATED)


@atomic()
def recover_order_submission(actor, account_id, submission_id):
    submission = _find_submission(actor, account_id, submission_id)
    if submission is None:
        raise NotFound(NOT_FOUND)
    _lock_authorized_wallet(actor, submission)
    _recover_order(submission, actor)
    return SubmissionResult(submission)
