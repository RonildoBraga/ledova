import logging
import time
from urllib.parse import urlsplit

import requests
from django.conf import settings
from django.core.cache import cache

from integrations.transak.exceptions import TransakApiError, TransakConfigurationError

logger = logging.getLogger(__name__)

# Cache key for the partner access token
TRANSAK_ACCESS_TOKEN_CACHE_KEY = "transak:partner_access_token"

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "host.docker.internal"})


def _configured_service_url(setting_name: str, value: str | None) -> str:
    candidate = (value or "").strip().rstrip("/")
    parsed = urlsplit(candidate)
    is_local_http = parsed.scheme == "http" and parsed.hostname in _LOCAL_HOSTS

    if (
        not candidate
        or (parsed.scheme != "https" and not is_local_http)
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise TransakConfigurationError(f"{setting_name} must be an explicit HTTPS URL (or a local HTTP test endpoint)")
    return candidate


class TransakClient:

    def __init__(self, api_key: str = None, api_secret: str = None):
        self.api_key = api_key or settings.TRANSAK_API_KEY
        self.api_secret = api_secret or settings.TRANSAK_API_SECRET

        if not self.api_key:
            raise TransakConfigurationError("TRANSAK_API_KEY is not configured")
        if not self.api_secret:
            raise TransakConfigurationError("TRANSAK_API_SECRET is not configured")

        self.api_url = _configured_service_url("TRANSAK_API_URL", settings.TRANSAK_API_URL)
        self.api_gateway_url = _configured_service_url("TRANSAK_API_GATEWAY_URL", settings.TRANSAK_API_GATEWAY_URL)
        self.referrer_domain = settings.TRANSAK_REFERRER_DOMAIN

    def _get_access_token(self) -> str:
        """Get a cached partner access token, refreshing if needed."""
        access_token = cache.get(TRANSAK_ACCESS_TOKEN_CACHE_KEY)
        if access_token:
            return access_token

        return self._refresh_access_token()

    def _refresh_access_token(self) -> str:
        """Call Transak's Refresh Access Token API to get a new partner access token.

        POST /partners/api/v2/refresh-token
        Body: {"apiKey": "..."}
        Header: api-secret: "..."
        Returns: {"data": {"accessToken": "...", "expiresAt": <unix_timestamp>}}
        """
        url = f"{self.api_url}/partners/api/v2/refresh-token"

        try:
            response = requests.post(
                url,
                json={"apiKey": self.api_key},
                headers={
                    "api-secret": self.api_secret,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                timeout=15,
            )
        except requests.RequestException as exc:
            raise TransakApiError("Transak access-token request failed") from exc

        if response.status_code != 200:
            raise TransakApiError(f"Transak access-token request failed with HTTP {response.status_code}")

        try:
            data = response.json().get("data", {})
        except ValueError as exc:
            raise TransakApiError("Transak access-token response was not valid JSON") from exc
        access_token = data.get("accessToken")
        expires_at = data.get("expiresAt")

        if not access_token:
            raise TransakApiError("No accessToken in refresh response")

        # Cache with a buffer before expiry (expire 1 hour early)
        if expires_at:
            ttl = max(int(expires_at - time.time() - 3600), 300)
        else:
            ttl = 6 * 24 * 3600  # 6 days fallback

        cache.set(TRANSAK_ACCESS_TOKEN_CACHE_KEY, access_token, ttl)
        logger.info(f"Transak partner access token refreshed, expires in {ttl}s")

        return access_token

    def create_secure_widget_url(
        self,
        wallet_address: str,
        network: str,
        crypto_currency_code: str = None,
        fiat_currency: str = None,
        default_fiat_currency: str = None,
        fiat_amount: float = None,
        default_fiat_amount: float = None,
        email: str = None,
        disable_wallet_address_form: bool = True,
        products_availed: str = "BUY",
        redirect_url: str = None,
        theme_color: str = None,
        hide_menu: bool = True,
        color_mode: str = "DARK",
        partner_customer_id: str = None,
    ) -> str:
        """Create a secure widget URL via Transak's Create Widget URL API.

        POST /api/v2/auth/session
        Body: {"widgetParams": {...}}
        Header: access-token: "..."
        Returns: {"data": {"widgetUrl": "..."}}

        The returned widgetUrl is valid for 5 minutes and can only be used once.
        """
        access_token = self._get_access_token()

        widget_params = {
            "apiKey": self.api_key,
            "referrerDomain": self.referrer_domain,
            "walletAddress": wallet_address,
            "network": network.lower(),
            "productsAvailed": products_availed,
        }

        if crypto_currency_code:
            widget_params["cryptoCurrencyCode"] = crypto_currency_code.upper()

        if fiat_currency:
            widget_params["fiatCurrency"] = fiat_currency.upper()

        if default_fiat_currency:
            widget_params["defaultFiatCurrency"] = default_fiat_currency.upper()

        if fiat_amount:
            widget_params["fiatAmount"] = str(int(fiat_amount))

        if default_fiat_amount:
            widget_params["defaultFiatAmount"] = str(int(default_fiat_amount))

        if email:
            widget_params["email"] = email

        if disable_wallet_address_form:
            widget_params["disableWalletAddressForm"] = True

        if redirect_url:
            widget_params["redirectURL"] = redirect_url

        if theme_color:
            widget_params["themeColor"] = theme_color

        if hide_menu:
            widget_params["hideMenu"] = True

        if color_mode:
            widget_params["colorMode"] = color_mode

        if partner_customer_id:
            widget_params["partnerCustomerId"] = partner_customer_id

        url = f"{self.api_gateway_url}/api/v2/auth/session"

        try:
            response = requests.post(
                url,
                json={"widgetParams": widget_params},
                headers={
                    "access-token": access_token,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                timeout=15,
            )
        except requests.RequestException as exc:
            raise TransakApiError("Transak widget-session request failed") from exc

        if response.status_code != 200:
            raise TransakApiError(f"Transak widget-session request failed with HTTP {response.status_code}")

        try:
            data = response.json().get("data", {})
        except ValueError as exc:
            raise TransakApiError("Transak widget-session response was not valid JSON") from exc
        widget_url = data.get("widgetUrl")

        if not widget_url:
            raise TransakApiError("No widgetUrl in create session response")

        return widget_url
