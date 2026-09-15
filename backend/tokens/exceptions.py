from rest_framework import status
from rest_framework.exceptions import APIException

from shared.utils.token_amounts import format_units


class InvalidSettlementAmountException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = (
        "The matched amount cannot be represented exactly in the deployed token's units "
        "within the supported settlement range."
    )
    default_code = "invalid_settlement_amount"
    expose_code = True


class OrderActionConflictException(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This action identifies different original order instructions."
    default_code = "action_intent_conflict"
    expose_code = True


class OrderActionContextException(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The order's signing context is unavailable or has changed. Recover this action before retrying."
    default_code = "action_context_conflict"
    expose_code = True


class OrderActionRefreshRequiredException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Request a new challenge bound to an order action."
    default_code = "action_refresh_required"
    expose_code = True


class OrderSubmissionConflictException(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This submission identifies different original order terms."
    default_code = "submission_conflict"
    expose_code = True


class OrderSubmissionRefreshRequiredException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Request a new challenge bound to this order submission."
    default_code = "submission_refresh_required"
    expose_code = True


class TokenFactoryNotConfiguredException(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "Token factory contract is not configured."
    default_code = "token_factory_not_configured"


class TokenDeploymentFailedException(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "Token deployment failed."
    default_code = "token_deployment_failed"


class InvalidTokenStateException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Token is not in the required state for this operation."
    default_code = "invalid_token_state"


class CapitalIncreaseConflict(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "This capital increase requires recovery of its original execution."
    default_code = "capital_increase_conflict"


class CapitalIncreaseUnresolved(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "The capital increase remains unresolved. Recover the original request."
    default_code = "capital_increase_unresolved"


class TokenPauseFailedException(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Token pause or unpause failed on chain."
    default_code = "token_pause_failed"


class IssuanceRefusedException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Issuance refused before any transaction was sent."
    default_code = "issuance_refused"


class CompanyNotReadyException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Company is not ready for this operation."
    default_code = "company_not_ready"


class InvalidTokenAddressException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Invalid token contract address."
    default_code = "invalid_token_address"


class InvalidRecipientAddressException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Invalid recipient address."
    default_code = "invalid_recipient_address"


class InvalidHolderAddressException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Invalid holder address."
    default_code = "invalid_holder_address"


class TokenBalanceRetrievalException(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "Failed to retrieve token balance."
    default_code = "token_balance_retrieval_failed"


class ContractLoadException(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "Failed to load contract."
    default_code = "contract_load_failed"


class NotWhitelistedException(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "Address is not whitelisted."
    default_code = "not_whitelisted"

    def __init__(self, address=None):
        if address:
            super().__init__(detail=f"Address {address} is not whitelisted")
        else:
            super().__init__()


class InsufficientBalanceException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Insufficient token balance."
    default_code = "insufficient_balance"

    def __init__(self, balance=None, required=None, token_symbol=None, decimals=0):
        if balance is not None and required is not None:
            token_str = f" {token_symbol}" if token_symbol else " tokens"
            balance_formatted = format_units(balance, decimals)
            required_formatted = format_units(required, decimals)
            super().__init__(
                detail=f"Insufficient balance: you have {balance_formatted}{token_str} but need {required_formatted}"
            )
        else:
            super().__init__()


class TokenPausedException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Token transfers are paused."
    default_code = "token_paused"


class CreateOrderNotWhitelistedException(NotWhitelistedException):
    pass


class CreateOrderInsufficientBalanceException(InsufficientBalanceException):
    pass


class TransferPreparationException(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "Failed to prepare transfer."
    default_code = "transfer_preparation_failed"


class TransferBroadcastException(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "Failed to broadcast transfer."
    default_code = "transfer_broadcast_failed"


class OrderCancellationException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Order cannot be cancelled."
    default_code = "order_cancellation_failed"


class OrderModificationException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Order cannot be modified."
    default_code = "order_modification_failed"


class OrderModificationConflictException(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Order has a pending swap and cannot be modified."
    default_code = "order_modification_conflict"


class OrderMatchException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Order matching failed."
    default_code = "order_match_failed"


class SwapSignatureException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Invalid swap signature."
    default_code = "swap_signature_invalid"


class SwapExecutionException(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "Swap execution failed."
    default_code = "swap_execution_failed"


class SwapNotReadyException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Swap order is not ready for execution."
    default_code = "swap_not_ready"


class SwapExpiredException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Swap order has expired."
    default_code = "swap_expired"


class AtomicSwapNotConfiguredException(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "AtomicSwap contract is not configured."
    default_code = "atomic_swap_not_configured"


class NAVUpdateConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This NAV submission cannot proceed with the supplied identity or state."
    default_code = "nav_update_conflict"


class SignatureRequiredException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Signature and message are required for this operation."
    default_code = "signature_required"


class InvalidSignatureException(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "Invalid signature - does not match the expected wallet address."
    default_code = "invalid_signature"


class DeployedShareClassException(APIException):

    status_code = status.HTTP_409_CONFLICT
    default_detail = "A deployed share class is a register of members and cannot be deleted."
    default_code = "deployed_share_class"

    def __init__(self, symbol: str):
        detail = (
            f"{symbol} is on chain and is the register of members for its holders, so it cannot be deleted, "
            "whatever its status. Pause it to stop transfers; the record is kept either way."
        )
        super().__init__(detail=detail)


class SigningChallengeException(APIException):
    expose_code = True


class ChallengeUnknownException(SigningChallengeException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "No signing challenge matches this signature. Request a new one."
    default_code = "challenge_unknown"


class ChallengeExpiredException(SigningChallengeException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "This signing challenge has expired. Request a new one."
    default_code = "challenge_expired"


class ChallengeAlreadyUsedException(SigningChallengeException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This signing challenge has already been used and cannot be used again."
    default_code = "challenge_already_used"


class ChallengeMismatchException(SigningChallengeException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "This signing challenge was not issued for this action."
    default_code = "challenge_mismatch"

    def __init__(self, what: str):
        super().__init__(detail=f"This signing challenge was not issued for this {what}.")


class RegisterUnavailableException(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = (
        "The share register cannot be produced because the chain could not be read. It is not shown from the "
        "allotment record, because a register that may be missing members cannot say so about itself. The "
        "allotments themselves are on the subscriptions and allotments listing."
    )


class WalletBalancesUnavailableException(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = (
        "The wallet's balances cannot be read because the chain could not be reached. An empty list is not "
        "returned instead, because it would say the wallet holds nothing."
    )


class MintRequestConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This mint request cannot be changed or retried in its recorded state."
    default_code = "mint_request_conflict"


class PauseChangeConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The earlier pause or unpause must resolve before another request can be admitted."
    default_code = "pause_change_conflict"


class IssuanceExecutionConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This issuance cannot be changed or retried in its recorded state."
    default_code = "issuance_execution_conflict"


class IssuanceExecutionUnresolved(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "The original share issuance requires recovery before its outcome is known."
    default_code = "issuance_execution_unresolved"


class IssuanceExecutionAdvanced(IssuanceExecutionConflict):
    default_detail = "Another worker advanced this issuance. Recover the committed attempt."


class MintRequestUnresolved(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "The mint outcome is unresolved. Recover this request instead of creating another mint."
    default_code = "mint_request_unresolved"


class SettlementContextChanged(APIException):
    status_code = 409
    default_detail = "The original swap context is no longer admitted. Review the recorded swap before continuing."
    default_code = "swap_settlement_context_changed"
    expose_code = True


class LegacySwapHeld(APIException):
    status_code = 409
    default_detail = (
        "This legacy swap is held for operator attribution. New approvals, signatures and execution are unavailable."
    )
    default_code = "legacy_swap_held"
    expose_code = True


class SettlementApprovalUncertain(Exception):
    def __init__(self, tx_hash):
        super().__init__("Approval outcome remains unconfirmed.")
        self.tx_hash = tx_hash
