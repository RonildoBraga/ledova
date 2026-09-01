from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from shared.views import AuthenticatedGenericViewSet
from tokens.services import ShareTokenService
from tokens.trading_wallet_access import resolve_verified_evm_wallets


class TradingWalletViewSet(AuthenticatedGenericViewSet):

    @action(detail=False, methods=["get"])
    def balances(self, request):
        wallet_address = request.query_params.get("wallet_address")

        if not wallet_address:
            raise ValidationError({"wallet_address": "This query parameter is required."})

        authorized_wallets = resolve_verified_evm_wallets(request.user, [wallet_address])

        token_service = ShareTokenService()
        result = token_service.get_wallet_token_balances(authorized_wallets.addresses[0])

        return Response(result, status=status.HTTP_200_OK)
