"""Factory for creating KYC provider instances."""

from django.conf import settings

from integrations.kyc.base import KYCProvider
from integrations.kyc.constants import PROVIDER_KYCAID, PROVIDER_SUMSUB


def get_kyc_provider() -> KYCProvider:
    """Return the configured KYC provider instance based on settings.KYC_PROVIDER."""
    provider = getattr(settings, "KYC_PROVIDER", PROVIDER_KYCAID)

    if provider == PROVIDER_KYCAID:
        from integrations.kycaid.client import KYCAIDService

        return KYCAIDService()

    if provider == PROVIDER_SUMSUB:
        from integrations.sumsub.client import SumSubService

        return SumSubService()

    raise ValueError(f"Unknown KYC provider: {provider}. Must be '{PROVIDER_KYCAID}' or '{PROVIDER_SUMSUB}'.")
