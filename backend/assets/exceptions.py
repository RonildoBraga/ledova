from rest_framework import status
from rest_framework.exceptions import APIException


class AssetNotFoundException(APIException):

    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "Asset not found."
    default_code = "asset_not_found"

    def __init__(self, asset_symbol=None):
        if asset_symbol:
            detail = f"Asset {asset_symbol} not found."
        else:
            detail = self.default_detail
        super().__init__(detail)


class InvalidAssetConfigurationException(APIException):

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "Asset has invalid configuration."
    default_code = "invalid_asset_configuration"

    def __init__(self, message=None):
        detail = message or self.default_detail
        super().__init__(detail)


class InvalidPriceDataException(APIException):

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Invalid price data."
    default_code = "invalid_price_data"

    def __init__(self, message=None):
        detail = message or self.default_detail
        super().__init__(detail)


class AssetSyncException(APIException):

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "Asset synchronization failed."
    default_code = "asset_sync_failed"

    def __init__(self, message=None):
        detail = message or self.default_detail
        super().__init__(detail)
