from rest_framework import status
from rest_framework.exceptions import APIException


class WhitelistEntryNotFoundException(APIException):

    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "Whitelist entry not found."
    default_code = "whitelist_entry_not_found"


class AddressAlreadyWhitelistedException(APIException):

    status_code = status.HTTP_409_CONFLICT
    default_detail = "This address is already whitelisted."
    default_code = "address_already_whitelisted"


class AddressNotWhitelistedException(APIException):

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "This address is not whitelisted."
    default_code = "address_not_whitelisted"


class WalletNotRegisteredException(APIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "No unique registered wallet matches this address."
    default_code = "wallet_not_registered"


class InvalidWalletAddressException(APIException):

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Invalid Ethereum wallet address format."
    default_code = "invalid_wallet_address"


class WhitelistOperationFailedException(APIException):

    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "Whitelist operation failed."
    default_code = "whitelist_operation_failed"

    def __init__(self, detail=None, tx_hash=None):
        self.tx_hash = tx_hash
        if detail:
            super().__init__(detail=detail)
        else:
            super().__init__()


class WhitelistSyncFailedException(APIException):

    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "Failed to sync whitelist with blockchain."
    default_code = "whitelist_sync_failed"


class WhitelistContractNotConfiguredException(APIException):

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Whitelist contract is not configured."
    default_code = "whitelist_contract_not_configured"


class InsufficientWhitelistPermissionsException(APIException):

    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "Operator does not have permission for whitelist operations."
    default_code = "insufficient_whitelist_permissions"


class BlockchainConnectionException(APIException):

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Unable to connect to blockchain network."
    default_code = "blockchain_connection_failed"


class TransactionFailedException(APIException):

    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "Blockchain transaction failed."
    default_code = "transaction_failed"

    def __init__(self, detail=None, tx_hash=None, reason=None):
        self.tx_hash = tx_hash
        self.reason = reason
        if detail:
            super().__init__(detail=detail)
        elif reason:
            super().__init__(detail=f"Transaction failed: {reason}")
        else:
            super().__init__()


class TransactionTimeoutException(APIException):

    status_code = status.HTTP_504_GATEWAY_TIMEOUT
    default_detail = "Blockchain transaction timed out."
    default_code = "transaction_timeout"

    def __init__(self, tx_hash=None, timeout_seconds=None):
        self.tx_hash = tx_hash
        self.timeout_seconds = timeout_seconds
        if tx_hash and timeout_seconds:
            detail = f"Transaction {tx_hash} timed out after {timeout_seconds} seconds."
            super().__init__(detail=detail)
        else:
            super().__init__()


class BatchEntriesRequiredException(APIException):

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "No entries provided for batch operation."
    default_code = "batch_entries_required"


class BatchSizeLimitExceededException(APIException):

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Batch size exceeds the maximum limit."
    default_code = "batch_size_limit_exceeded"

    def __init__(self, max_size=100):
        detail = f"Maximum {max_size} entries per batch."
        super().__init__(detail=detail)
