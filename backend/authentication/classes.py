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

    def _get_token_and_source(self, request):
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
