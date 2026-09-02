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


class WalletAlreadyInPortfolioException(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Wallet is already in this portfolio."
    default_code = "wallet_already_in_portfolio"
