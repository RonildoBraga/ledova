from rest_framework import status
from rest_framework.exceptions import APIException


class WalletAlreadyExistsException(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "A wallet with this address already exists."
    default_code = "wallet_already_exists"


class WalletNotVerifiedException(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "This wallet has not been verified yet."
    default_code = "wallet_not_verified"


class InvalidWalletAddressException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "The provided wallet address is invalid."
    default_code = "invalid_wallet_address"


class InvalidSignatureException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "The signature verification failed. Please ensure you signed the correct message."
    default_code = "invalid_signature"


class BlockchainNotSupportedException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "This blockchain is not supported."
    default_code = "blockchain_not_supported"


class WalletBalanceFetchException(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Unable to fetch wallet balance from blockchain. Please try again later."
    default_code = "wallet_balance_fetch_failed"


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


class WalletBalanceSyncException(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Failed to sync wallet balance from blockchain. Please try again later."
    default_code = "wallet_balance_sync_failed"


class InsufficientBalanceException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Insufficient balance to complete this transaction."
    default_code = "insufficient_balance"


class InvalidTransactionException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "The transaction parameters are invalid."
    default_code = "invalid_transaction"


class TransactionBroadcastException(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "Failed to broadcast transaction to blockchain network."
    default_code = "transaction_broadcast_failed"


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
