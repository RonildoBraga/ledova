from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from assets import views as asset_views
from authentication import views as auth_views
from feature_flags import views as feature_flag_views
from integrations.alchemy import AlchemyWebhookView
from integrations.kycaid.crypto_webhook import KYCAIDCryptoWebhookView
from integrations.kycaid.webhook import KYCAIDWebhookView
from integrations.sumsub import SumSubWebhookView
from portfolios import views as portfolio_views
from users import views as user_views
from wallets import views as wallet_views

admin.site.site_header = "Ledova CRM"
admin.site.site_title = "Ledova Admin Portal"
admin.site.index_title = "Welcome to Ledova Client Management"

router = DefaultRouter()
router.register(r"", auth_views.AuthViewSet, basename="auth")
router.register(r"user-profiles", user_views.UserProfileViewSet, basename="user-profiles")
router.register(r"user-preferences", user_views.UserPreferencesViewSet, basename="user-preferences")
router.register(r"financial-profiles", user_views.FinancialProfileViewSet, basename="financial-profiles")
router.register(r"user-accounts", user_views.UserAccountViewSet, basename="user-accounts")
router.register(
    r"investor-classifications", user_views.InvestorClassificationViewSet, basename="investor-classifications"
)
router.register(r"device-tokens", user_views.DeviceTokenViewSet, basename="device-tokens")
router.register(
    r"notification-preferences", user_views.NotificationPreferencesViewSet, basename="notification-preferences"
)
router.register(r"notifications", user_views.NotificationViewSet, basename="notifications")
router.register(r"transactions", wallet_views.TransactionViewSet, basename="transactions")
router.register(r"wallets", wallet_views.WalletViewSet, basename="wallets")
router.register(r"fiat-purchases", wallet_views.FiatPurchaseViewSet, basename="fiat-purchases")
router.register(r"portfolios", portfolio_views.PortfolioViewSet, basename="portfolios")
router.register(r"favourite-assets", user_views.FavouriteAssetViewSet, basename="favourite-assets")
router.register(r"assets", asset_views.AssetViewSet, basename="assets")
router.register(r"feature-flags", feature_flag_views.FeatureFlagViewSet, basename="feature-flags")

identity_verification_router = DefaultRouter()
identity_verification_router.register(r"", user_views.IdentityVerificationViewSet, basename="identity-verification")

urlpatterns = [
    path("api/users/identity-verification/", include(identity_verification_router.urls)),
    path("webhooks/sumsub/", SumSubWebhookView.as_view(), name="sumsub-webhook"),
    path("webhooks/kycaid/", KYCAIDWebhookView.as_view(), name="kycaid-webhook"),
    path("webhooks/kycaid/crypto/", KYCAIDCryptoWebhookView.as_view(), name="kycaid-crypto-webhook"),
    path("webhooks/alchemy/", AlchemyWebhookView.as_view(), name="alchemy-webhook"),
    path("api/operator/", include("operators.urls", namespace="operators")),
    path("api/v1/companies/", include("companies.urls", namespace="companies")),
    path("api/v1/tokens/", include("tokens.urls", namespace="tokens")),
    path("api/v1/whitelist/", include("whitelist.urls", namespace="whitelist")),
    path("api/v1/trading/", include("tokens.urls_trading", namespace="trading")),
    path("api/v1/documents/", include("documents.urls", namespace="documents")),
    path("api/", include(router.urls)),
    path("admin/", admin.site.urls),
    path("api-auth/", include("rest_framework.urls", namespace="rest_framework")),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
