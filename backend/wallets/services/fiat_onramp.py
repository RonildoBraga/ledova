import logging
from decimal import Decimal

from integrations.transak import TransakClient
from integrations.transak.exceptions import TransakError

logger = logging.getLogger(__name__)


def generate_transak_widget_url(
    wallet_address: str,
    chain: str,
    crypto_currency_code: str = None,
    fiat_currency: str = None,
    default_fiat_currency: str = None,
    fiat_amount: Decimal = None,
    default_fiat_amount: Decimal = None,
    email: str = None,
    disable_wallet_address_form: bool = True,
    products_availed: str = "BUY",
    redirect_url: str = None,
    theme_color: str = None,
    hide_menu: bool = True,
    color_mode: str = "DARK",
    partner_customer_id: str = None,
) -> str:
    try:
        logger.info(
            f"Generating Transak widget URL for address {wallet_address[:8]}... ({chain}/{crypto_currency_code})"
        )

        client = TransakClient()
        widget_url = client.create_secure_widget_url(
            wallet_address=wallet_address,
            network=chain,
            crypto_currency_code=crypto_currency_code,
            fiat_currency=fiat_currency,
            default_fiat_currency=default_fiat_currency,
            fiat_amount=float(fiat_amount) if fiat_amount else None,
            default_fiat_amount=float(default_fiat_amount) if default_fiat_amount else None,
            email=email,
            disable_wallet_address_form=disable_wallet_address_form,
            products_availed=products_availed,
            redirect_url=redirect_url,
            theme_color=theme_color,
            hide_menu=hide_menu,
            color_mode=color_mode,
            partner_customer_id=partner_customer_id,
        )

        logger.info("Successfully generated Transak widget URL")
        return widget_url

    except TransakError as e:
        logger.error(f"Failed to generate Transak widget URL ({e.__class__.__name__}: {str(e)})")
        raise
