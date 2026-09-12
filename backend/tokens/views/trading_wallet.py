from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from integrations.base_chain.exceptions import BaseChainConnectionError
from shared.views import AuthenticatedGenericViewSet
from tokens.exceptions import WalletBalancesUnavailableException
from tokens.serializers.trading_wallet import TradingWalletBalancesSerializer
from tokens.services import ShareTokenService
from tokens.trading_wallet_access import resolve_verified_evm_wallets


class TradingWalletViewSet(AuthenticatedGenericViewSet):
    unscoped_by_the_base_because = (
        "it serves no queryset: balances is detail=False and reads the chain, and the wallet it reads "
        "comes from resolve_verified_evm_wallets, which scopes to the principal."
    )

    @extend_schema(
        parameters=[OpenApiParameter("wallet_address", OpenApiTypes.STR, OpenApiParameter.QUERY, required=True)],
        responses=TradingWalletBalancesSerializer,
    )
    @action(detail=False, methods=["get"])
    def balances(self, request):
        wallet_address = request.query_params.get("wallet_address")

        if not wallet_address:
            raise ValidationError({"wallet_address": "This query parameter is required."})

        authorized_wallets = resolve_verified_evm_wallets(request.user, [wallet_address])

        try:
            token_service = ShareTokenService()
            result = token_service.get_wallet_token_balances(authorized_wallets.addresses[0])
        except BaseChainConnectionError as exc:
            raise WalletBalancesUnavailableException(
                f"{WalletBalancesUnavailableException.default_detail} The chain could not be reached."
            ) from exc

        return Response(result, status=status.HTTP_200_OK)
