"""
Exceptions for Transak API integration.
"""


class TransakError(Exception):
    """Base exception for Transak errors."""


class TransakConfigurationError(TransakError):
    """Exception raised when Transak is not properly configured."""


class TransakApiError(TransakError):
    """Exception raised when a Transak API call fails."""
