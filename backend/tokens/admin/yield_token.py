import logging

from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse

from tokens.models import NAVUpdate, YieldToken
from tokens.services import YieldTokenService

from ._helpers import action_buttons
from .mintable_token import MintableTokenAdmin

logger = logging.getLogger(__name__)


class NAVUpdateForm(forms.Form):
    nav_per_token = forms.DecimalField(
        max_digits=20,
        decimal_places=6,
        min_value=0.000001,
        label="NAV per Token (USD)",
        help_text="New NAV per token in USD (e.g., 1.005000 for $1.005)",
        widget=forms.NumberInput(attrs={"step": "0.000001", "style": "width: 200px;"}),
    )

    total_reserve_value = forms.DecimalField(
        max_digits=20,
        decimal_places=6,
        min_value=0,
        label="Synthetic Reference Value (USD)",
        help_text="Synthetic scenario value used by this experimental token model",
        widget=forms.NumberInput(attrs={"step": "0.01", "style": "width: 200px;"}),
    )

    custodian_report_ref = forms.CharField(
        max_length=200,
        required=False,
        label="Scenario Reference",
        help_text="Optional reference for the synthetic scenario (for example, a test case ID)",
    )

    update_on_chain = forms.BooleanField(
        initial=False,
        required=False,
        label="Execute on local/testnet chain",
        help_text="Also call updateNAV() on the configured local chain or supported public testnet",
    )

    notes = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        label="Notes (Optional)",
    )


@admin.register(YieldToken)
class YieldTokenAdmin(MintableTokenAdmin):
    mint_request_field = "yield_token"
    list_display = [
        "name",
        "symbol",
        "contract_address_short",
        "nav_display",
        "total_reserve_display",
        "last_nav_update",
        "is_active_badge",
        "actions_column",
    ]
    list_filter = ["is_active"]
    readonly_fields = [
        "uuid",
        "nav_per_token",
        "total_reserve_value",
        "last_nav_update",
        "created_at",
        "updated_at",
    ]

    fieldsets = [
        (None, {"fields": ["uuid", "name", "symbol", "contract_address", "decimals", "is_active"]}),
        ("NAV Information", {"fields": ["nav_per_token", "total_reserve_value", "last_nav_update"]}),
        ("Timestamps", {"fields": ["created_at", "updated_at"], "classes": ["collapse"]}),
    ]

    def get_urls(self):
        update_nav = path(
            "<uuid:uuid>/update-nav/",
            self.admin_site.admin_view(self.update_nav_view),
            name="tokens_yieldtoken_update_nav",
        )
        return [update_nav] + super().get_urls()

    @admin.display(description="NAV/Token")
    def nav_display(self, obj):
        return f"${obj.nav_per_token:,.6f}" if obj.nav_per_token else "-"

    @admin.display(description="Synthetic Reference Value")
    def total_reserve_display(self, obj):
        return f"${obj.total_reserve_value:,.2f}" if obj.total_reserve_value else "-"

    @admin.display(description="Actions")
    def actions_column(self, obj):
        if not obj.is_active or not obj.contract_address:
            return "-"
        nav_url = reverse("admin:tokens_yieldtoken_update_nav", args=[obj.uuid])
        return action_buttons([("Update NAV", nav_url, "#007bff"), ("+ Mint", self.mint_url(obj), "#28a745")])

    def update_nav_view(self, request, uuid):
        yield_token = get_object_or_404(YieldToken, uuid=uuid)

        if not yield_token.is_active:
            messages.error(request, f"Cannot update NAV: {yield_token.symbol} is not active")
            return HttpResponseRedirect(reverse("admin:tokens_yieldtoken_change", args=[yield_token.pk]))

        nav_info = None
        is_nav_updater = False
        try:
            if yield_token.contract_address:
                service = YieldTokenService(contract_address=yield_token.contract_address)
                nav_info = service.get_nav_info()
                is_nav_updater = service.is_nav_updater(service.signer_address)
        except Exception as e:
            logger.warning(f"Failed to fetch on-chain NAV info for {yield_token.symbol}: {e}")

        recent_updates = NAVUpdate.objects.filter(yield_token=yield_token)[:5]

        if request.method == "POST":
            form = NAVUpdateForm(request.POST)
            if form.is_valid():
                try:
                    service = YieldTokenService(contract_address=yield_token.contract_address)
                    nav_update = service.update_nav(
                        new_nav_per_token=form.cleaned_data["nav_per_token"],
                        total_reserve_value=form.cleaned_data["total_reserve_value"],
                        user=request.user,
                        yield_token=yield_token,
                        custodian_report_ref=form.cleaned_data.get("custodian_report_ref", ""),
                        notes=form.cleaned_data.get("notes", ""),
                        update_on_chain=form.cleaned_data.get("update_on_chain", False),
                    )

                    messages.success(
                        request,
                        f"NAV updated for {yield_token.symbol}: "
                        f"${nav_update.old_nav_per_token} → ${nav_update.new_nav_per_token}",
                    )
                    return HttpResponseRedirect(reverse("admin:tokens_yieldtoken_change", args=[yield_token.pk]))

                except Exception as e:
                    messages.error(request, f"NAV update failed: {e}")
        else:
            initial = {}
            if yield_token.nav_per_token:
                initial["nav_per_token"] = yield_token.nav_per_token
            if yield_token.total_reserve_value:
                initial["total_reserve_value"] = yield_token.total_reserve_value
            form = NAVUpdateForm(initial=initial)

        context = {
            **self.admin_site.each_context(request),
            "title": f"Update NAV — {yield_token.symbol}",
            "subtitle": None,
            "yield_token": yield_token,
            "form": form,
            "opts": self.model._meta,
            "nav_info": nav_info,
            "is_nav_updater": is_nav_updater,
            "recent_updates": recent_updates,
        }
        return render(request, "admin/tokens/yieldtoken/update_nav_form.html", context)


@admin.register(NAVUpdate)
class NAVUpdateAdmin(admin.ModelAdmin):
    list_display = [
        "yield_token",
        "nav_change_display",
        "total_reserve_value",
        "custodian_report_ref",
        "updated_by",
        "created_at",
    ]
    list_filter = ["yield_token"]
    readonly_fields = [
        "uuid",
        "yield_token",
        "old_nav_per_token",
        "new_nav_per_token",
        "total_reserve_value",
        "custodian_report_ref",
        "transaction",
        "updated_by",
        "notes",
        "created_at",
        "updated_at",
    ]
    ordering = ["-created_at"]

    @admin.display(description="NAV Change")
    def nav_change_display(self, obj):
        return f"${obj.old_nav_per_token} → ${obj.new_nav_per_token}"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
