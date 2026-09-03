from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from integrations.kyc.base import KYCProvider
from integrations.kyc.constants import PROVIDER_KYCAID, PROVIDER_SUMSUB


def get_kyc_provider() -> KYCProvider:
    provider = settings.KYC_PROVIDER

    if provider == PROVIDER_KYCAID:
        from integrations.kycaid.client import KYCAIDService

        return KYCAIDService()

    if provider == PROVIDER_SUMSUB:
        from integrations.sumsub.client import SumSubService

        return SumSubService()

    raise ImproperlyConfigured(f'KYC_PROVIDER is {provider!r}; set it to "{PROVIDER_SUMSUB}" or "{PROVIDER_KYCAID}".')
