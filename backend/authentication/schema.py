from django.conf import settings
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.utils import OpenApiParameter, extend_schema_field
from rest_framework import serializers


class HybridJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "authentication.classes.HybridJWTAuthentication"
    name = ["bearerAuth", "cookieAuth"]

    def get_security_requirement(self, auto_schema):
        return [{name: []} for name in self.name]

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


class AuthTokenPairSerializer(serializers.Serializer):
    access_token = serializers.CharField()
    refresh_token = serializers.CharField()


class AuthRefreshErrorSerializer(serializers.Serializer):
    error = serializers.CharField()
