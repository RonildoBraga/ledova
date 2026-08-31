from rest_framework import status
from rest_framework.exceptions import APIException


class TransactionNotFoundException(APIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "Transaction not found."
    default_code = "transaction_not_found"


class TransactionNotFailedException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Transaction is not in a failed state."
    default_code = "transaction_not_failed"


class MaxRetryCountReachedException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Maximum retry count reached."
    default_code = "max_retry_reached"


class BlockchainClientException(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "Blockchain client error."
    default_code = "blockchain_client_error"
