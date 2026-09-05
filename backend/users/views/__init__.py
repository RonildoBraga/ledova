from users.views.device_token import DeviceTokenViewSet
from users.views.favourite_asset import FavouriteAssetViewSet
from users.views.financial_profile import FinancialProfileViewSet
from users.views.identity_verification import IdentityVerificationViewSet
from users.views.notification import NotificationViewSet
from users.views.notification_preferences import NotificationPreferencesViewSet
from users.views.user_account import UserAccountViewSet
from users.views.user_preferences import UserPreferencesViewSet
from users.views.user_profile import UserProfileViewSet

__all__ = [
    "DeviceTokenViewSet",
    "FavouriteAssetViewSet",
    "FinancialProfileViewSet",
    "NotificationViewSet",
    "IdentityVerificationViewSet",
    "NotificationPreferencesViewSet",
    "UserAccountViewSet",
    "UserPreferencesViewSet",
    "UserProfileViewSet",
]
