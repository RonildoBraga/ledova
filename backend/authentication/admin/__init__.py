"""
Admin package for authentication app.
"""

from authentication.admin.user import CustomUserAdmin
from authentication.admin.user_token import UserTokenAdmin

__all__ = [
    "CustomUserAdmin",
    "UserTokenAdmin",
]
