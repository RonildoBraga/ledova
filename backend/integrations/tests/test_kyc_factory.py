from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from integrations.kyc import get_kyc_provider
from integrations.kycaid.client import KYCAIDService
from integrations.sumsub.client import SumSubService


class KYCProviderFactoryTest(SimpleTestCase):
    @override_settings(KYC_PROVIDER="sumsub", SUMSUB_API_KEY="k", SUMSUB_SECRET_KEY="s", SUMSUB_BASE_URL="")
    def test_sumsub_is_selected_explicitly(self):
        self.assertIsInstance(get_kyc_provider(), SumSubService)

    @override_settings(KYC_PROVIDER="kycaid", KYCAID_API_TOKEN="", KYCAID_BASE_URL="")
    def test_kycaid_is_selected_explicitly(self):
        self.assertIsInstance(get_kyc_provider(), KYCAIDService)

    def test_unset_or_unknown_provider_is_a_configuration_error_not_a_silent_default(self):
        for value in ("", "acme"):
            with self.subTest(value=value), override_settings(KYC_PROVIDER=value):
                with self.assertRaisesMessage(ImproperlyConfigured, 'set it to "sumsub" or "kycaid"'):
                    get_kyc_provider()
