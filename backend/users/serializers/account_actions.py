from rest_framework import serializers


class DeletedAccountResponseSerializer(serializers.Serializer):
    message = serializers.CharField()


class ExportedUserSerializer(serializers.Serializer):
    email = serializers.EmailField()
    date_joined = serializers.DateTimeField()
    is_email_verified = serializers.BooleanField()


class ExportedProfileSerializer(serializers.Serializer):
    full_name = serializers.CharField(allow_null=True, allow_blank=True)
    date_of_birth = serializers.DateField(allow_null=True)
    phone_country_code = serializers.CharField(allow_null=True, allow_blank=True)
    phone_number = serializers.CharField(allow_null=True, allow_blank=True)
    residential_address = serializers.CharField(allow_null=True, allow_blank=True)
    citizenship_country = serializers.CharField(allow_null=True)
    is_id_verified = serializers.BooleanField()
    created_at = serializers.DateTimeField()


class ExportedPreferencesSerializer(serializers.Serializer):
    selected_portfolio = serializers.UUIDField(allow_null=True)
    selected_account = serializers.UUIDField(allow_null=True)


class ExportedFinancialProfileSerializer(serializers.Serializer):
    occupation = serializers.CharField(allow_null=True, allow_blank=True)
    source_of_funds = serializers.JSONField(allow_null=True)
    source_of_funds_other_text = serializers.CharField(allow_null=True, allow_blank=True)
    intended_use = serializers.CharField(allow_null=True, allow_blank=True)
    intended_use_other_text = serializers.CharField(allow_null=True, allow_blank=True)


class ExportedAccountSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    account_number = serializers.CharField()
    account_type = serializers.CharField()
    activation_date = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()


class ExportedWalletSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    name = serializers.CharField(allow_null=True, allow_blank=True)
    chain = serializers.CharField()
    address = serializers.CharField()
    native_balance = serializers.CharField()
    market_value = serializers.CharField()
    is_verified = serializers.BooleanField()
    created_at = serializers.DateTimeField()


class ExportedTransactionSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    tx_hash = serializers.CharField()
    chain = serializers.CharField()
    status = serializers.CharField()
    asset = serializers.CharField(allow_null=True)
    amount = serializers.CharField()
    transaction_fee = serializers.CharField(allow_null=True)
    from_address = serializers.CharField()
    to_address = serializers.CharField(allow_null=True, allow_blank=True)
    block_timestamp = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()


class ExportedPortfolioSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    name = serializers.CharField()
    is_active = serializers.BooleanField()
    created_at = serializers.DateTimeField()


class AccountExportDataSerializer(serializers.Serializer):
    exported_at = serializers.DateTimeField()
    user = ExportedUserSerializer()
    profile = ExportedProfileSerializer(allow_null=True)
    preferences = ExportedPreferencesSerializer(allow_null=True)
    financial_profile = ExportedFinancialProfileSerializer(allow_null=True)
    accounts = ExportedAccountSerializer(many=True)
    wallets = ExportedWalletSerializer(many=True)
    transactions = ExportedTransactionSerializer(many=True)
    portfolios = ExportedPortfolioSerializer(many=True)
