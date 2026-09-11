REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ("authentication.classes.HybridJWTAuthentication",),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_RENDERER_CLASSES": (
        "djangorestframework_camel_case.render.CamelCaseJSONRenderer",
        "djangorestframework_camel_case.render.CamelCaseBrowsableAPIRenderer",
    ),
    "DEFAULT_PARSER_CLASSES": (
        "djangorestframework_camel_case.parser.CamelCaseJSONParser",
        "djangorestframework_camel_case.parser.CamelCaseFormParser",
        "djangorestframework_camel_case.parser.CamelCaseMultiPartParser",
    ),
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "auth": "60/min",
        "auth_email": "10/hour",
        "anon": "200/min",
        "user": "1000/min",
        "order_write": "30/min",
        "broadcast": "10/min",
    },
    "EXCEPTION_HANDLER": "shared.api.exceptions.custom_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Ledova API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "ENUM_NAME_OVERRIDES": {
        "CapitalRequestStatusEnum": "tokens.models.choices.RequestStatus",
        "CompanyStatusEnum": "companies.models.company.CompanyStatus",
        "OfferingStatusEnum": "offerings.models.offering.OfferingStatus",
        "ShareTokenStatusEnum": "tokens.models.choices.ShareTokenStatus",
        "SubscriptionStatusEnum": "offerings.models.subscription.SubscriptionStatus",
        "SupportedWalletChainEnum": "shared.constants.supported_chain_choices",
        "SwapOrderStatusEnum": "tokens.models.choices.SwapOrderStatus",
        "TransferOrderStatusEnum": "tokens.models.choices.TransferOrderStatus",
        "TransferOrderTypeEnum": "tokens.models.choices.TransferOrderType",
        "UserDocumentTypeEnum": "documents.models.document.DocumentType",
        "UserVerificationStatusEnum": "integrations.kyc.constants.VERIFICATION_STATUS_CHOICES",
        "WalletSigningPreferenceEnum": "wallets.models.wallet.WalletSigningPreference.choices",
    },
    "POSTPROCESSING_HOOKS": [
        "drf_spectacular.hooks.postprocess_schema_enums",
        "drf_spectacular.contrib.djangorestframework_camel_case.camelize_serializer_fields",
        "shared.api.schema_hooks.document_trading_events_stream",
    ],
}
