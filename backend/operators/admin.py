from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.shortcuts import render
from django.urls import reverse

from documents.services.access import deployment_mode_error
from operators.models import Operator
from operators.services import (
    REGISTRANT_NOTE,
    configuration_health,
    registrants,
    worklist,
)
from operators.settlement import settlement_errors


class OperatorForm(forms.ModelForm):
    class Meta:
        model = Operator
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        mode_error = deployment_mode_error(cleaned.get("deployment_mode"))
        if mode_error:
            self.add_error("deployment_mode", mode_error)
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
        operator = Operator.get()
        context = {
            **self.admin_site.each_context(request),
            **(extra_context or {}),
            "title": "Operator console",
            "opts": self.model._meta,
            "configuration_url": reverse("admin:operators_operator_change", args=[operator.pk]),
            "worklist": worklist(),
            "health": configuration_health(),
            "deployment_mode": operator.get_deployment_mode_display(),
            "registrants": registrants(),
            "registrant_note": REGISTRANT_NOTE,
        }
        return render(request, "admin/operators/operator/console.html", context)

    def has_add_permission(self, request):
        return not Operator.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
