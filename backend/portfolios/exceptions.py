from rest_framework import status
from rest_framework.exceptions import APIException


class PortfolioNotFoundException(APIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "Portfolio not found."
    default_code = "portfolio_not_found"

    def __init__(self, portfolio_uuid=None):
        if portfolio_uuid:
            detail = f"Portfolio {portfolio_uuid} not found."
        else:
            detail = self.default_detail
        super().__init__(detail)


class InactivePortfolioException(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Cannot perform operations on an inactive portfolio."
    default_code = "inactive_portfolio"

    def __init__(self, portfolio_uuid=None):
        if portfolio_uuid:
            detail = f"Portfolio {portfolio_uuid} is inactive and cannot be modified."
        else:
            detail = self.default_detail
        super().__init__(detail)


class InvalidAllocationException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Invalid portfolio allocation configuration."
    default_code = "invalid_allocation"

    def __init__(self, message=None):
        detail = message or self.default_detail
        super().__init__(detail)


class DuplicateAllocationException(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Asset allocation already exists for this portfolio."
    default_code = "duplicate_allocation"

    def __init__(self, asset_symbol=None):
        if asset_symbol:
            detail = f"Allocation for {asset_symbol} already exists in this portfolio."
        else:
            detail = self.default_detail
        super().__init__(detail)


class InsufficientHoldingException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Insufficient holding quantity."
    default_code = "insufficient_holding"

    def __init__(self, asset_symbol=None, available=None, requested=None):
        self.asset_symbol = asset_symbol
        self.available = available
        self.requested = requested

        if asset_symbol and available is not None and requested is not None:
            detail = f"Insufficient holding for {asset_symbol}. Available: {available}, Requested: {requested}"
        else:
            detail = self.default_detail
        super().__init__(detail)


class PortfolioCalculationException(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "Portfolio calculation failed."
    default_code = "calculation_error"

    def __init__(self, calculation_type=None, message=None):
        if calculation_type and message:
            detail = f"{calculation_type} calculation failed: {message}"
        elif calculation_type:
            detail = f"{calculation_type} calculation failed."
        else:
            detail = self.default_detail
        super().__init__(detail)


class WalletNotFoundException(APIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "Wallet not found."
    default_code = "wallet_not_found"

    def __init__(self, wallet_uuid=None):
        if wallet_uuid:
            detail = f"Wallet {wallet_uuid} not found."
        else:
            detail = self.default_detail
        super().__init__(detail)


class WalletOwnershipException(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "Wallet does not belong to this user account."
    default_code = "wallet_ownership_mismatch"


class WalletAlreadyInPortfolioException(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Wallet is already in this portfolio."
    default_code = "wallet_already_in_portfolio"


class WalletNotInPortfolioException(APIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "Wallet is not in this portfolio."
    default_code = "wallet_not_in_portfolio"
