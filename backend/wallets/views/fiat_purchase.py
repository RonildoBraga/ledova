from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from shared.constants import get_native_asset_symbol
from wallets.exceptions import WalletUuidRequiredException
from wallets.models import Wallet
from wallets.services.fiat_onramp import generate_transak_widget_url


class FiatPurchaseViewSet(viewsets.ViewSet):

    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["post"], url_path="transak-widget-url")
    def transak_widget_url(self, request):
        wallet_uuid = request.data.get("wallet_uuid")
        if not wallet_uuid:
            raise WalletUuidRequiredException()

        wallet = get_object_or_404(Wallet.objects.visible_to_user(request.user), uuid=wallet_uuid)

        crypto_currency_code = request.data.get("crypto_currency_code")
        if not crypto_currency_code:
            crypto_currency_code = get_native_asset_symbol(wallet.chain)

        chain = wallet.chain

        fiat_currency = request.data.get("fiat_currency")
        default_fiat_currency = request.data.get("default_fiat_currency", "AUD")
        fiat_amount = request.data.get("fiat_amount")
        default_fiat_amount = request.data.get("default_fiat_amount")

        email = request.user.email
        partner_customer_id = str(request.user.pk)

        theme_color = request.data.get("theme_color") or getattr(settings, "TRANSAK_THEME_COLOR", "")
        redirect_url = request.data.get("redirect_url")

        widget_url = generate_transak_widget_url(
            wallet_address=wallet.address,
            chain=chain,
            crypto_currency_code=crypto_currency_code,
            fiat_currency=fiat_currency,
            default_fiat_currency=default_fiat_currency,
            fiat_amount=fiat_amount,
            default_fiat_amount=default_fiat_amount,
            email=email,
            disable_wallet_address_form=True,
            products_availed="BUY",
            redirect_url=redirect_url,
            theme_color=theme_color,
            hide_menu=True,
            color_mode="DARK",
            partner_customer_id=partner_customer_id,
        )

        return Response(
            {
                "url": widget_url,
                "walletAddress": wallet.address,
                "chain": chain,
                "cryptoCurrency": crypto_currency_code,
            }
        )
