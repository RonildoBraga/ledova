from rest_framework import status
from rest_framework.exceptions import APIException


class TokenFactoryNotConfiguredException(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "Token factory contract is not configured."
    default_code = "token_factory_not_configured"

    def __init__(self, detail=None):
        if detail:
            super().__init__(detail=detail)
        else:
            super().__init__()


class OperatorKeyNotConfiguredException(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "Operator private key is not configured."
    default_code = "operator_key_not_configured"


class TokenDeploymentFailedException(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "Token deployment failed."
    default_code = "token_deployment_failed"

    def __init__(self, detail=None):
        if detail:
            super().__init__(detail=f"Token deployment failed: {detail}")
        else:
            super().__init__()


class TokenNotFoundException(APIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "Token not found."
    default_code = "token_not_found"


class InvalidTokenStateException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Token is not in the required state for this operation."
    default_code = "invalid_token_state"

    def __init__(self, detail=None):
        if detail:
            super().__init__(detail=detail)
        else:
            super().__init__()


class CompanyNotReadyException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Company is not ready for this operation."
    default_code = "company_not_ready"

    def __init__(self, detail=None):
        if detail:
            super().__init__(detail=detail)
        else:
            super().__init__()


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


class TokenInfoRetrievalException(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "Failed to retrieve token information."
    default_code = "token_info_retrieval_failed"


class TokenBalanceRetrievalException(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "Failed to retrieve token balance."
    default_code = "token_balance_retrieval_failed"


class ContractLoadException(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "Failed to load contract."
    default_code = "contract_load_failed"

    def __init__(self, detail=None):
        if detail:
            super().__init__(detail=f"Failed to load contract: {detail}")
        else:
            super().__init__()


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

    def __init__(self, detail=None):
        if detail:
            super().__init__(detail=f"Transfer preparation failed: {detail}")
        else:
            super().__init__()


class TransferBroadcastException(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "Failed to broadcast transfer."
    default_code = "transfer_broadcast_failed"

    def __init__(self, detail=None):
        if detail:
            super().__init__(detail=f"Transfer broadcast failed: {detail}")
        else:
            super().__init__()


class OrderNotFoundException(APIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "Order not found."
    default_code = "order_not_found"


class OrderCancellationException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Order cannot be cancelled."
    default_code = "order_cancellation_failed"

    def __init__(self, detail=None):
        if detail:
            super().__init__(detail=detail)
        else:
            super().__init__()


class OrderModificationException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Order cannot be modified."
    default_code = "order_modification_failed"

    def __init__(self, detail=None):
        if detail:
            super().__init__(detail=detail)
        else:
            super().__init__()


class OrderModificationConflictException(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Order has a pending swap and cannot be modified."
    default_code = "order_modification_conflict"

    def __init__(self, detail=None):
        if detail:
            super().__init__(detail=detail)
        else:
            super().__init__()


class OrderMatchException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Order matching failed."
    default_code = "order_match_failed"

    def __init__(self, detail=None):
        if detail:
            super().__init__(detail=detail)
        else:
            super().__init__()


class CapitalIncreaseSubmissionException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Failed to submit capital increase request."
    default_code = "capital_increase_submission_failed"

    def __init__(self, detail=None):
        if detail:
            super().__init__(detail=detail)
        else:
            super().__init__()


class SwapOrderNotFoundException(APIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "Swap order not found."
    default_code = "swap_order_not_found"


class SwapSignatureException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Invalid swap signature."
    default_code = "swap_signature_invalid"

    def __init__(self, detail=None):
        if detail:
            super().__init__(detail=detail)
        else:
            super().__init__()


class SwapExecutionException(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "Swap execution failed."
    default_code = "swap_execution_failed"

    def __init__(self, detail=None):
        if detail:
            super().__init__(detail=f"Swap execution failed: {detail}")
        else:
            super().__init__()


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

    def __init__(self, detail=None):
        if detail:
            super().__init__(detail=f"Stablecoin minting failed: {detail}")
        else:
            super().__init__()


class StablecoinBurnFailedException(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "Stablecoin burning failed."
    default_code = "stablecoin_burn_failed"

    def __init__(self, detail=None):
        if detail:
            super().__init__(detail=f"Stablecoin burning failed: {detail}")
        else:
            super().__init__()


class YieldTokenContractNotConfiguredException(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "Yield token contract is not configured."
    default_code = "yield_token_contract_not_configured"


class YieldTokenMintFailedException(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "Yield token minting failed."
    default_code = "yield_token_mint_failed"

    def __init__(self, detail=None):
        if detail:
            super().__init__(detail=f"Yield token minting failed: {detail}")
        else:
            super().__init__()


class YieldTokenNAVUpdateFailedException(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "Yield token NAV update failed."
    default_code = "yield_token_nav_update_failed"

    def __init__(self, detail=None):
        if detail:
            super().__init__(detail=f"NAV update failed: {detail}")
        else:
            super().__init__()


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

    def __init__(self, detail=None):
        if detail:
            super().__init__(detail=detail)
        else:
            super().__init__()


class ShareIssuanceFailedException(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "Share issuance failed."
    default_code = "share_issuance_failed"

    def __init__(self, detail=None):
        if detail:
            super().__init__(detail=f"Share issuance failed: {detail}")
        else:
            super().__init__()
