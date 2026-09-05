from rest_framework import serializers

from companies.models import Company, CompanyStatus
from companies.serializers.document import CompanyDocumentSerializer
from companies.services.company import register_company
from wallets.models import Wallet


class _CompanyUserProfileSerializer(serializers.Serializer):

    email = serializers.EmailField(read_only=True)
    full_name = serializers.CharField(read_only=True)


class _CompanyUserProfileCreateSerializer(serializers.Serializer):

    first_name = serializers.CharField(max_length=100, required=True)
    last_name = serializers.CharField(max_length=100, required=True)
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True)


class CompanyListSerializer(serializers.ModelSerializer):

    status_display = serializers.CharField(source="get_status_display", read_only=True)
    company_type_display = serializers.CharField(
        source="get_company_type_display",
        read_only=True,
    )

    class Meta:
        model = Company
        fields = [
            "uuid",
            "name",
            "trading_name",
            "display_name",
            "acn",
            "company_type",
            "company_type_display",
            "status",
            "status_display",
            "industry",
            "city",
            "state",
            "is_active",
            "is_approved",
            "created_at",
        ]
        read_only_fields = fields


class CompanyDetailSerializer(serializers.ModelSerializer):

    status_display = serializers.CharField(source="get_status_display", read_only=True)
    company_type_display = serializers.CharField(
        source="get_company_type_display",
        read_only=True,
    )
    email = serializers.EmailField(read_only=True)
    primary_contact = _CompanyUserProfileSerializer(read_only=True)
    documents = CompanyDocumentSerializer(many=True, read_only=True)
    operator_wallet = serializers.SlugRelatedField(slug_field="uuid", read_only=True)

    class Meta:
        model = Company
        fields = [
            "uuid",
            "name",
            "trading_name",
            "display_name",
            "company_type",
            "company_type_display",
            "acn",
            "abn",
            "status",
            "status_display",
            "email",
            "phone",
            "address_line_1",
            "address_line_2",
            "city",
            "state",
            "postcode",
            "country",
            "operator_wallet",
            "submitted_at",
            "review_started_at",
            "approved_at",
            "activated_at",
            "info_requested_at",
            "info_request_reason",
            "additional_info_response",
            "description",
            "industry",
            "founded_year",
            "is_active",
            "is_approved",
            "is_pending_review",
            "can_issue_tokens",
            "primary_contact",
            "documents",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "uuid",
            "status",
            "email",
            "submitted_at",
            "review_started_at",
            "approved_at",
            "activated_at",
            "info_requested_at",
            "info_request_reason",
            "additional_info_response",
            "api_key",
            "is_active",
            "is_approved",
            "is_pending_review",
            "can_issue_tokens",
            "created_at",
            "updated_at",
        ]


class CompanyRegistrationSerializer(serializers.ModelSerializer):

    primary_contact = _CompanyUserProfileCreateSerializer(write_only=True, required=True)

    class Meta:
        model = Company
        fields = [
            "name",
            "trading_name",
            "company_type",
            "acn",
            "abn",
            "primary_contact",
        ]

    def validate_acn(self, value):
        acn = value.replace(" ", "").replace("-", "")
        if not acn.isdigit() or len(acn) != 9:
            raise serializers.ValidationError("ACN must be exactly 9 digits.")
        return acn

    def validate_abn(self, value):
        if not value:
            return value
        abn = value.replace(" ", "").replace("-", "")
        if not abn.isdigit() or len(abn) != 11:
            raise serializers.ValidationError("ABN must be exactly 11 digits.")
        return abn

    def create(self, validated_data):
        contact_data = validated_data.pop("primary_contact")
        user = self.context["request"].user

        return register_company(owner=user, primary_contact_data=contact_data, **validated_data)


class CompanyUpdateSerializer(serializers.ModelSerializer):

    operator_wallet = serializers.SlugRelatedField(
        slug_field="uuid", queryset=Wallet.objects.none(), required=False, allow_null=True
    )

    class Meta:
        model = Company
        fields = [
            "name",
            "trading_name",
            "company_type",
            "acn",
            "abn",
            "address_line_1",
            "address_line_2",
            "city",
            "state",
            "postcode",
            "phone",
            "description",
            "industry",
            "operator_wallet",
        ]

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")
        fields["operator_wallet"].queryset = Wallet.objects.visible_to_user(
            getattr(request, "user", None)
        ).verified_evm()
        return fields

    def validate_acn(self, value):
        instance = self.instance
        if instance and instance.status != CompanyStatus.DRAFT:
            if value != instance.acn:
                raise serializers.ValidationError("ACN cannot be changed after registration is submitted.")
        acn = value.replace(" ", "").replace("-", "")
        if not acn.isdigit() or len(acn) != 9:
            raise serializers.ValidationError("ACN must be exactly 9 digits.")
        return acn

    def validate_abn(self, value):
        instance = self.instance
        if instance and instance.status != CompanyStatus.DRAFT:
            if value != instance.abn:
                raise serializers.ValidationError("ABN cannot be changed after registration is submitted.")
        if not value:
            return value
        abn = value.replace(" ", "").replace("-", "")
        if not abn.isdigit() or len(abn) != 11:
            raise serializers.ValidationError("ABN must be exactly 11 digits.")
        return abn

    def validate_company_type(self, value):
        instance = self.instance
        if instance and instance.status != CompanyStatus.DRAFT:
            if value != instance.company_type:
                raise serializers.ValidationError("Company type cannot be changed after registration is submitted.")
        return value


class CompanyAPIKeySerializer(serializers.Serializer):

    api_key = serializers.CharField(read_only=True)
    api_key_created_at = serializers.DateTimeField(read_only=True)


class CompanyStatusUpdateSerializer(serializers.Serializer):

    status = serializers.ChoiceField(choices=CompanyStatus.choices)
    reason = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        new_status = data["status"]

        if new_status in [
            CompanyStatus.REJECTED,
            CompanyStatus.SUSPENDED,
            CompanyStatus.WARNING,
            CompanyStatus.DELISTED,
            CompanyStatus.INFO_REQUIRED,
        ] and not data.get("reason"):
            raise serializers.ValidationError({"reason": f"Reason is required when changing status to {new_status}."})

        return data


class ApplicationSubmitSerializer(serializers.Serializer):

    confirm = serializers.BooleanField(
        required=True,
        help_text="Confirm that all information is accurate and complete.",
    )

    def validate_confirm(self, value):
        if not value:
            raise serializers.ValidationError("You must confirm that all information is accurate and complete.")
        return value


class ApplicationResubmitSerializer(serializers.Serializer):

    response = serializers.CharField(
        required=True,
        help_text="Response to the information request.",
    )


class ApplicationWithdrawSerializer(serializers.Serializer):

    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Optional reason for withdrawal.",
    )


class ApplicationStatusSerializer(serializers.ModelSerializer):

    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Company
        fields = [
            "uuid",
            "name",
            "status",
            "status_display",
            "submitted_at",
            "review_started_at",
            "info_requested_at",
            "info_request_reason",
            "approved_at",
            "activated_at",
            "rejection_reason",
            "rejection_at",
            "is_pending_review",
            "is_approved",
            "is_active",
        ]
        read_only_fields = fields
