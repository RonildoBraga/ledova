"""
Models package for authentication app.
"""

from authentication.models.user import CustomUser
from authentication.models.user_token import UserToken

__all__ = [
    "CustomUser",
    "UserToken",
]
