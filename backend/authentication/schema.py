from django.conf import settings
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.utils import OpenApiParameter, extend_schema_field
from rest_framework import serializers
from rest_framework.permissions import SAFE_METHODS


class HybridJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "authentication.classes.HybridJWTAuthentication"
    name = ["bearerAuth", "cookieAuth", "csrfHeader", "csrfCookie", "refreshCookie"]

    def get_security_requirement(self, auto_schema):
        cookie_name = "refreshCookie" if getattr(auto_schema.view, "action", None) == "token_refresh" else "cookieAuth"
        cookie = {cookie_name: []}
        if auto_schema.method not in SAFE_METHODS:
            cookie.update(csrfHeader=[], csrfCookie=[])
        return [{"bearerAuth": []}, cookie]

    def get_security_definition(self, auto_schema):
        return [
            {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "A live session access JWT in the Authorization header.",
            },
            {
                "type": "apiKey",
                "in": "cookie",
                "name": settings.AUTH_COOKIE["access"],
                "description": (
                    "A live session access JWT in the configured cookie. Unsafe cookie-authenticated requests "
                    "must pass Django's CSRF token and origin checks."
                ),
            },
            {
                "type": "apiKey",
                "in": "header",
                "name": settings.CSRF_HEADER_NAME.removeprefix("HTTP_").replace("_", "-"),
                "description": (
                    "CSRF token matching the CSRF cookie or session secret. Cookie-authenticated unsafe JSON "
                    "requests require this header. POST form and multipart requests may instead supply "
                    "csrfmiddlewaretoken in the body. The header alternative works for every unsafe method."
                ),
            },
            {
                "type": "apiKey",
                "in": "cookie",
                "name": settings.SESSION_COOKIE_NAME if settings.CSRF_USE_SESSIONS else settings.CSRF_COOKIE_NAME,
                "description": (
                    "Session cookie identifying stored CSRF state."
                    if settings.CSRF_USE_SESSIONS
                    else (
                        "CSRF cookie set by /api/auth/verify/ or cookie sign-in. "
                        "Its token can be sent in the CSRF header."
                    )
                ),
            },
            {
                "type": "apiKey",
                "in": "cookie",
                "name": settings.AUTH_COOKIE["refresh"],
                "description": (
                    "Refresh JWT used by /api/token/refresh/ when no truthy refresh body value is supplied "
                    "and X-Auth-Transport is not bearer. No access cookie is required. Cookie refresh without "
                    "an Authorization header enforces CSRF independently of access authentication."
                ),
            },
        ]


AUTH_TRANSPORT_PARAMETER = OpenApiParameter(
    name="X-Auth-Transport",
    location=OpenApiParameter.HEADER,
    type=str,
    required=False,
    description=(
        "The value bearer, ignoring case and surrounding whitespace, selects bearer transport. "
        "Omitting the header or sending any other value uses cookie transport. "
        "This chooses how tokens are read or returned; it does not authenticate the request."
    ),
)


@extend_schema_field(
    {
        "oneOf": [
            {"type": "string", "nullable": True},
            {"type": "number", "enum": [0]},
            {"type": "boolean", "enum": [False]},
            {"type": "array", "items": {}, "maxItems": 0},
            {"type": "object", "maxProperties": 0},
        ]
    }
)
class AuthRefreshTokenField(serializers.JSONField):
    pass


class AuthRefreshRequestSerializer(serializers.Serializer):
    refresh = AuthRefreshTokenField(
        required=False,
        allow_null=True,
        help_text=(
            "Refresh JWT. In cookie transport, an omitted or falsy value falls back to the refresh cookie. "
            "Using a refresh cookie without an Authorization header requires CSRF validation. "
            "Bearer transport does not fall back to a refresh cookie."
        ),
    )


class AuthSignoutRequestSerializer(serializers.Serializer):
    refresh = AuthRefreshTokenField(
        required=False,
        allow_null=True,
        help_text=(
            "Refresh JWT to revoke when the request authenticates with a live access token. If omitted, "
            "authenticated signout revokes the access token's session. Anonymous signout only clears cookies; "
            "it does not revoke a supplied refresh token."
        ),
    )


class AuthTokenPairSerializer(serializers.Serializer):
    access_token = serializers.CharField()
    refresh_token = serializers.CharField()


class AuthRefreshErrorSerializer(serializers.Serializer):
    error = serializers.CharField()
