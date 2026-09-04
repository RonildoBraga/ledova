import logging

from django.conf import settings
from rest_framework import HTTP_HEADER_ENCODING
from rest_framework.authentication import CSRFCheck
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import SAFE_METHODS
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken

from authentication.services.tokens import TokenService

logger = logging.getLogger(__name__)


class HybridJWTAuthentication(JWTAuthentication):
    """
    Extends simplejwt JWTAuthentication to support both authentication methods:
    1. Cookie-based authentication (via 'access' cookie)
    2. Header-based authentication (via standard Authorization header)

    Auth failures return None (anonymous) instead of raising, letting the
    permission class decide — AllowAny endpoints proceed, protected endpoints
    return 401 via DRF's standard permission denial.

    A browser sends the access cookie on its own, so a cookie-sourced unsafe
    request must also carry the CSRF token (DRF views are csrf_exempt, which
    makes this the enforcement point); a Bearer header cannot be forged
    cross-site, so header-sourced requests skip the check.

    The header wins when both are presented: React Native's cookie jar replays
    the `access` cookie set at sign-in next to the mobile app's Bearer token,
    and that cookie must neither trigger the CSRF check nor, once stale, shadow
    a valid Bearer token. The dashboard never sends an Authorization header.
    """

    def _get_token_and_source(self, request):
        """Returns (raw_token, source) where source is 'header' or 'cookie'."""
        auth_header = self.get_header(request)
        if auth_header:
            parts = auth_header.split()
            if len(parts) == 2:
                auth_header_types = settings.SIMPLE_JWT.get("AUTH_HEADER_TYPES", ("Bearer",))
                if isinstance(auth_header_types, str):
                    auth_header_types = (auth_header_types,)
                header_type = parts[0].decode(HTTP_HEADER_ENCODING).lower()
                if header_type in {auth_type.lower() for auth_type in auth_header_types}:
                    return parts[1].decode(HTTP_HEADER_ENCODING), "header"

        token = request.COOKIES.get(settings.AUTH_COOKIE["access"])
        return (token, "cookie") if token else (None, None)

    def authenticate(self, request):
        raw_token, source = self._get_token_and_source(request)
        if raw_token is None:
            return None

        try:
            validated_token = self.get_validated_token(raw_token)

            # An access token is only as live as the refresh token it was issued with.
            if not TokenService.is_session_live(validated_token.get("rjti")):
                raise InvalidToken("Token has been revoked")

            user = self.get_user(validated_token)

        except Exception as e:
            logger.debug(f"{source} auth failed, proceeding as anonymous: {e}")
            return None

        if source == "cookie" and request.method not in SAFE_METHODS:
            self.enforce_csrf(request)

        return user, validated_token

    @staticmethod
    def enforce_csrf(request):
        check = CSRFCheck(lambda r: None)
        check.process_request(request)
        reason = check.process_view(request, None, (), {})
        if reason:
            raise PermissionDenied(f"CSRF Failed: {reason}")
