"""
Managers package for authentication app.
"""

from authentication.managers.user import (
    CustomUserManager,
    V2EmailLookupResult,
    V2EmailLookupState,
)

__all__ = [
    "CustomUserManager",
    "V2EmailLookupResult",
    "V2EmailLookupState",
]
