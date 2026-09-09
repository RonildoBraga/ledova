from rest_framework import status
from rest_framework.exceptions import APIException


class InvalidSignatureException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "The signature verification failed. Please ensure you signed the correct message."
    default_code = "invalid_signature"


class BlockchainAPIError(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "Failed to communicate with blockchain API. Please try again later."
    default_code = "blockchain_api_error"


class SignatureRequiredException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Signature is required for wallet verification."
    default_code = "signature_required"


class VerificationChallengeNotFoundException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "No verification challenge found. Please request a new challenge."
    default_code = "verification_challenge_not_found"


class VerificationChallengeExpiredException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "This verification challenge has expired. Please request a new challenge and sign it again."
    default_code = "verification_challenge_expired"


class InsufficientBalanceException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Insufficient balance to complete this transaction."
    default_code = "insufficient_balance"


class NativeAssetUnavailableException(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Native asset configuration for this network is unavailable. Contact support before retrying."
    default_code = "native_asset_unavailable"


class InvalidTransactionException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "The transaction parameters are invalid."
    default_code = "invalid_transaction"


class WalletUuidRequiredException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Wallet UUID is required."
    default_code = "wallet_uuid_required"


class UnsupportedChainException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "unsupported_chain"

    def __init__(self, chain: str):
        detail = f"{chain} is not currently supported for transfers."
        super().__init__(detail=detail)
