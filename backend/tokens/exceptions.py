from rest_framework import status
from rest_framework.exceptions import APIException


class TokenFactoryNotConfiguredException(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "Token factory contract is not configured."
    default_code = "token_factory_not_configured"


class OperatorKeyNotConfiguredException(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "Operator private key is not configured."
    default_code = "operator_key_not_configured"


class TokenDeploymentFailedException(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "Token deployment failed."
    default_code = "token_deployment_failed"


class InvalidTokenStateException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Token is not in the required state for this operation."
    default_code = "invalid_token_state"


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
            if decimals > 0:
                divisor = 10**decimals
                balance_formatted = f"{balance / divisor:,.{decimals}f}"
                required_formatted = f"{required / divisor:,.{decimals}f}"
            else:
                balance_formatted = f"{balance:,}"
                required_formatted = f"{required:,}"
            super().__init__(
                detail=f"Insufficient balance: you have {balance_formatted}{token_str} but need {required_formatted}"
            )
        else:
            super().__init__()


class TokenPausedException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Token transfers are paused."
    default_code = "token_paused"


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


class StablecoinContractNotConfiguredException(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "Stablecoin contract is not configured."
    default_code = "stablecoin_contract_not_configured"


class StablecoinMintFailedException(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "Stablecoin minting failed."
    default_code = "stablecoin_mint_failed"


class YieldTokenContractNotConfiguredException(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "Yield token contract is not configured."
    default_code = "yield_token_contract_not_configured"


class YieldTokenMintFailedException(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "Yield token minting failed."
    default_code = "yield_token_mint_failed"


class YieldTokenNAVUpdateFailedException(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "Yield token NAV update failed."
    default_code = "yield_token_nav_update_failed"


class NotAuthorizedMinterException(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "Address is not authorized as a minter."
    default_code = "not_authorized_minter"

    def __init__(self, address=None):
        if address:
            super().__init__(detail=f"Address {address} is not authorized as a minter")
        else:
            super().__init__()


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
