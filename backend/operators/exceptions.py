from rest_framework import status
from rest_framework.exceptions import APIException


class SettlementAssetNotDeployedException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "The settlement asset has no active deployment on the operator's receiving chain."
    default_code = "settlement_asset_not_deployed"
