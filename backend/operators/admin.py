from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect
from django.urls import reverse

from operators.models import Operator
from operators.settlement import settlement_errors


class OperatorForm(forms.ModelForm):
    class Meta:
        model = Operator
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        chain = cleaned.get("receiving_wallet_chain")
        if not chain:
            return cleaned
        errors = {}
        issued = cleaned.get("issued_stablecoin")
        if issued is not None:
            errors.update(settlement_errors([issued], "issued_stablecoin", chain))
        assets = cleaned.get("supported_settlement_assets")
        if assets is not None:
            errors.update(settlement_errors(assets, "supported_settlement_assets", chain))
        if errors:
            raise ValidationError(errors)
        return cleaned


@admin.register(Operator)
class OperatorAdmin(admin.ModelAdmin):

    form = OperatorForm
    readonly_fields = ["created_at", "updated_at"]
    filter_horizontal = ["supported_settlement_assets"]
    fieldsets = [
        ("Identity", {"fields": ["name", "legal_name", "abn", "contact_email", "website"]}),
        (
            "Deployment",
            {
                "fields": ["deployment_mode"],
                "description": (
                    "Single issuer: one company runs this instance for its own shares. "
                    "Registry: a provider hosts many companies."
                ),
            },
        ),
        (
            "Payments",
            {
                "fields": [
                    "bank_account_name",
                    "bank_bsb",
                    "bank_account_number",
                    "payment_reference_prefix",
                    "receiving_wallet_address",
                    "receiving_wallet_chain",
                    "issued_stablecoin",
                    "supported_settlement_assets",
                ],
                "description": (
                    "Where investors pay: the operator's AUD bank account and/or a wallet receiving a supported "
                    "stablecoin. Only authenticated users can read these through the API, and only once set."
                ),
            },
        ),
        ("Eligibility", {"fields": ["investor_kyc_required", "issuer_kyc_required"]}),
        ("Timestamps", {"fields": ["created_at", "updated_at"], "classes": ["collapse"]}),
    ]

    def changelist_view(self, request, extra_context=None):
        return HttpResponseRedirect(reverse("admin:operators_operator_change", args=[Operator.get().pk]))

    def has_add_permission(self, request):
        return not Operator.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
