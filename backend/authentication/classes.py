"""
Contains custom authentication classes for use with Django REST Framework.
"""

import logging

from django.conf import settings
from rest_framework import HTTP_HEADER_ENCODING
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken

from authentication.services.tokens import TokenService
from shared.utils.logging_utils import LoggingContext

logger = logging.getLogger("ledova_backend")


class HybridJWTAuthentication(JWTAuthentication):
    """
    Extends simplejwt JWTAuthentication to support both authentication methods:
    1. Cookie-based authentication (via 'access' cookie)
    2. Header-based authentication (via standard Authorization header)

    Auth failures return None (anonymous) instead of raising, letting the
    permission class decide — AllowAny endpoints proceed, protected endpoints
    return 401 via DRF's standard permission denial.
    """

    def _get_token_and_source(self, request):
        """Returns (raw_token, source) where source is 'cookie' or 'header'."""
        if hasattr(request, "COOKIES"):
            token = request.COOKIES.get(settings.AUTH_COOKIE["access"])
            if token:
                return token, "cookie"

        if hasattr(request, "META"):
            auth_header = self.get_header(request)
            if auth_header:
                parts = auth_header.split()

                if len(parts) == 2:
                    auth_header_types = settings.SIMPLE_JWT.get("AUTH_HEADER_TYPES", ("Bearer",))
                    if isinstance(auth_header_types, str):
                        auth_header_types = (auth_header_types,)

                    header_type = parts[0].decode(HTTP_HEADER_ENCODING).lower()
                    for auth_type in auth_header_types:
                        if header_type == auth_type.lower():
                            return parts[1].decode(HTTP_HEADER_ENCODING), "header"

        return None, None

    def authenticate(self, request):
        raw_token, source = self._get_token_and_source(request)
        if raw_token is None:
            return None

        try:
            validated_token = self.get_validated_token(raw_token)

            # An access token is only as live as the refresh token it was issued with.
            if not TokenService.is_session_live(validated_token.get("rjti")):
                raise InvalidToken("Token has been revoked")

            return self.get_user(validated_token), validated_token

        except Exception as e:
            logger.debug(f"{LoggingContext.AUTH} {source} auth failed, proceeding as anonymous: {e}")
            return None
