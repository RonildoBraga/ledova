"""
Serializers package for users app.
"""

from users.serializers.device_token import (
    DeviceTokenSerializer,
    RegisterDeviceTokenSerializer,
    UnregisterDeviceTokenSerializer,
)
from users.serializers.favourite_asset import FavouriteAssetSerializer
from users.serializers.financial_profile import FinancialProfileSerializer
from users.serializers.notification import NotificationSerializer
from users.serializers.notification_preferences import NotificationPreferencesSerializer
from users.serializers.user_account import UserAccountSerializer
from users.serializers.user_preferences import UserPreferencesSerializer
from users.serializers.user_profile import UserProfileSerializer
from users.serializers.waitlist import WaitlistCreateSerializer

__all__ = [
    "DeviceTokenSerializer",
    "FavouriteAssetSerializer",
    "FinancialProfileSerializer",
    "NotificationSerializer",
    "NotificationPreferencesSerializer",
    "RegisterDeviceTokenSerializer",
    "UnregisterDeviceTokenSerializer",
    "UserAccountSerializer",
    "UserPreferencesSerializer",
    "UserProfileSerializer",
    "WaitlistCreateSerializer",
]
