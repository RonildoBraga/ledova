from django.urls import reverse
from django.utils import timezone
from rest_framework import serializers

from companies.models import Company
from shared.uploads import validate_upload
from users.models.investor_classification import (
    DECLARATION_TEXT,
    InvestorCategory,
    InvestorClassification,
    InvestorClassificationStatus,
    plus_years,
)
from users.models.user_account import UserAccount

CERTIFIER_FIELDS = ("certificate_issued_at", "certifier_name", "certifier_body", "certifier_membership_number")


class InvestorClassificationSerializer(serializers.ModelSerializer):

    user_account = serializers.PrimaryKeyRelatedField(queryset=UserAccount.objects.none())
    company = serializers.PrimaryKeyRelatedField(queryset=Company.objects.none(), required=False, allow_null=True)

    category_display = serializers.CharField(source="get_category_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    is_live = serializers.BooleanField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)

    evidence_file = serializers.FileField(write_only=True)
    evidence_url = serializers.SerializerMethodField()

    class Meta:
        model = InvestorClassification
        fields = [
            "uuid",
            "user_account",
            "company",
            "category",
            "category_display",
            "status",
            "status_display",
            "declaration_accepted",
            "declaration_text",
            "declared_basis",
            "evidence_file",
            "evidence_url",
            "evidence_file_size",
            "evidence_mime_type",
            "certificate_issued_at",
            "certifier_name",
            "certifier_body",
            "certifier_membership_number",
            "submitted_at",
            "reviewed_at",
            "review_notes",
            "rejection_reason",
            "expires_at",
            "is_live",
            "is_expired",
            "created_at",
        ]
        read_only_fields = [
            "uuid",
            "status",
            "declaration_text",
            "evidence_file_size",
            "evidence_mime_type",
            "submitted_at",
            "reviewed_at",
            "review_notes",
            "rejection_reason",
            "expires_at",
            "created_at",
        ]

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            fields["user_account"].queryset = UserAccount.objects.visible_to_user(user)
            fields["company"].queryset = Company.objects.active()
        return fields

    def get_evidence_url(self, obj):
        if not obj.evidence_file:
            return None
        url = reverse("investor-classifications-evidence", args=[obj.uuid])
        request = self.context.get("request")
        return request.build_absolute_uri(url) if request else url

    def validate_declaration_accepted(self, value):
        if not value:
            raise serializers.ValidationError("The declaration must be accepted.")
        return value

    def _validate_company(self, attrs):
        category = attrs.get("category")
        company = attrs.get("company")
        if category == InvestorCategory.ASSOCIATED_PERSON and company is None:
            raise serializers.ValidationError({"company": "An associated person claim must name the issuer."})
        if category != InvestorCategory.ASSOCIATED_PERSON and company is not None:
            raise serializers.ValidationError({"company": "Only an associated person claim is scoped to a company."})

    def _validate_certificate(self, attrs):
        if attrs.get("category") != InvestorCategory.ACCOUNTANT_CERTIFICATE:
            return
        missing = [field for field in CERTIFIER_FIELDS if not attrs.get(field)]
        if missing:
            raise serializers.ValidationError(
                {field: "This field is required for an accountant's certificate." for field in missing}
            )
        if plus_years(attrs["certificate_issued_at"]) <= timezone.now():
            raise serializers.ValidationError(
                {"certificate_issued_at": "The certificate must have been issued within the last two years."}
            )

    def validate(self, attrs):
        self._validate_company(attrs)
        self._validate_certificate(attrs)

        account = attrs.get("user_account")
        open_submissions = InvestorClassification.objects.filter(
            user_account=account, status=InvestorClassificationStatus.SUBMITTED
        )
        if open_submissions.exists():
            raise serializers.ValidationError(
                {"user_account": "This account already has a classification awaiting review."}
            )

        attrs["evidence_file_size"], attrs["evidence_mime_type"] = validate_upload(
            attrs["evidence_file"], field="evidence_file"
        )
        attrs["declaration_text"] = DECLARATION_TEXT[InvestorCategory(attrs["category"])]
        attrs["submitted_at"] = timezone.now()
        return attrs


class InvestorEligibilitySerializer(serializers.Serializer):
    is_eligible = serializers.BooleanField()
    reasons = serializers.ListField(child=serializers.CharField())
    account = serializers.SerializerMethodField()
    classification = serializers.SerializerMethodField()

    def get_account(self, obj):
        return str(obj.account.uuid) if obj.account else None

    def get_classification(self, obj):
        if obj.classification is None:
            return None
        return InvestorClassificationSerializer(obj.classification, context=self.context).data
