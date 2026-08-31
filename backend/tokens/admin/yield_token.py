import logging

from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from tokens.models import MintRequest, NAVUpdate, YieldToken
from tokens.services import YieldTokenService

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


class MintForm(forms.Form):
    recipient_address = forms.CharField(
        max_length=42,
        label="Recipient Address",
        help_text="Ethereum wallet address (0x...)",
        widget=forms.TextInput(attrs={"style": "width: 100%; font-family: monospace;"}),
    )

    recipient_name = forms.CharField(
        max_length=200,
        label="Recipient Name",
        help_text="Name of the recipient (for audit trail)",
    )

    amount = forms.DecimalField(
        max_digits=20,
        decimal_places=6,
        min_value=0.000001,
        label="Amount (synthetic AUSG)",
        help_text="Synthetic token amount (e.g., 100.000000). Will be converted to raw units.",
    )

    deposit_reference = forms.CharField(
        max_length=100,
        label="Scenario Reference",
        help_text="Synthetic scenario reference or test case ID",
    )

    deposit_date = forms.DateField(
        label="Scenario Date",
        help_text="Date assigned to the synthetic scenario",
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    notes = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        label="Notes (Optional)",
    )

    def clean_recipient_address(self):
        address = self.cleaned_data["recipient_address"]
        if not address.startswith("0x") or len(address) != 42:
            raise forms.ValidationError("Invalid Ethereum address format. Must be 42 characters starting with 0x.")
        return address

    def clean_amount(self):
        return self.cleaned_data["amount"]


@admin.register(YieldToken)
class YieldTokenAdmin(admin.ModelAdmin):
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
    search_fields = ["name", "symbol", "contract_address"]
    readonly_fields = [
        "uuid",
        "nav_per_token",
        "total_reserve_value",
        "last_nav_update",
        "created_at",
        "updated_at",
    ]
    ordering = ["symbol"]

    fieldsets = [
        (
            None,
            {
                "fields": ["uuid", "name", "symbol", "contract_address", "decimals", "is_active"],
            },
        ),
        (
            "NAV Information",
            {
                "fields": ["nav_per_token", "total_reserve_value", "last_nav_update"],
            },
        ),
        (
            "Timestamps",
            {
                "fields": ["created_at", "updated_at"],
                "classes": ["collapse"],
            },
        ),
    ]

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<uuid:uuid>/update-nav/",
                self.admin_site.admin_view(self.update_nav_view),
                name="tokens_yieldtoken_update_nav",
            ),
            path(
                "<uuid:uuid>/mint/",
                self.admin_site.admin_view(self.mint_view),
                name="tokens_yieldtoken_mint",
            ),
        ]
        return custom_urls + urls

    def contract_address_short(self, obj):
        if obj.contract_address:
            return f"{obj.contract_address[:10]}...{obj.contract_address[-8:]}"
        return "-"

    contract_address_short.short_description = "Contract"

    def nav_display(self, obj):
        if obj.nav_per_token:
            return f"${obj.nav_per_token:,.6f}"
        return "-"

    nav_display.short_description = "NAV/Token"

    def total_reserve_display(self, obj):
        if obj.total_reserve_value:
            return f"${obj.total_reserve_value:,.2f}"
        return "-"

    total_reserve_display.short_description = "Synthetic Reference Value"

    def is_active_badge(self, obj):
        if obj.is_active:
            return mark_safe(
                '<span style="background-color: #28a745; color: white; padding: 3px 8px; '
                'border-radius: 3px; font-size: 11px;">Active</span>'
            )
        return mark_safe(
            '<span style="background-color: #dc3545; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px;">Inactive</span>'
        )

    is_active_badge.short_description = "Status"

    def actions_column(self, obj):
        if not obj.is_active or not obj.contract_address:
            return "-"

        nav_url = reverse("admin:tokens_yieldtoken_update_nav", args=[obj.uuid])
        mint_url = reverse("admin:tokens_yieldtoken_mint", args=[obj.uuid])
        return format_html(
            '<a href="{}" style="display: inline-block; padding: 4px 10px; '
            "background-color: #007bff; color: white; text-decoration: none; "
            'border-radius: 4px; font-size: 11px; font-weight: bold; margin-right: 4px;">Update NAV</a>'
            '<a href="{}" style="display: inline-block; padding: 4px 10px; '
            "background-color: #28a745; color: white; text-decoration: none; "
            'border-radius: 4px; font-size: 11px; font-weight: bold;">+ Mint</a>',
            nav_url,
            mint_url,
        )

    actions_column.short_description = "Actions"

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

    def mint_view(self, request, uuid):
        yield_token = get_object_or_404(YieldToken, uuid=uuid)

        if not yield_token.is_active:
            messages.error(request, f"Cannot mint: {yield_token.symbol} is not active")
            return HttpResponseRedirect(reverse("admin:tokens_yieldtoken_change", args=[yield_token.pk]))

        if not yield_token.contract_address:
            messages.error(request, f"Cannot mint: {yield_token.symbol} has no contract address")
            return HttpResponseRedirect(reverse("admin:tokens_yieldtoken_change", args=[yield_token.pk]))

        try:
            service = YieldTokenService(contract_address=yield_token.contract_address)
            total_supply = service.get_total_supply()
            decimals = yield_token.decimals
            total_supply_display = f"{total_supply / (10 ** decimals):,.{decimals}f}"
            is_minter = service.is_minter(service.signer_address)
        except Exception as e:
            logger.error(f"Failed to get yield token info: {e}")
            total_supply_display = "Error"
            is_minter = False

        if request.method == "POST":
            form = MintForm(request.POST)
            if form.is_valid():
                amount_tokens = form.cleaned_data["amount"]
                amount_raw = int(amount_tokens * (10**yield_token.decimals))

                mint_request = MintRequest.objects.create(
                    yield_token=yield_token,
                    recipient_address=form.cleaned_data["recipient_address"],
                    recipient_name=form.cleaned_data["recipient_name"],
                    amount=amount_raw,
                    deposit_reference=form.cleaned_data["deposit_reference"],
                    deposit_date=form.cleaned_data["deposit_date"],
                    notes=form.cleaned_data.get("notes", ""),
                    requested_by=request.user,
                )

                try:
                    tx_hash, tx_record = service.mint(
                        to_address=form.cleaned_data["recipient_address"],
                        amount=amount_raw,
                        related_model="tokens.MintRequest",
                        related_uuid=str(mint_request.uuid),
                    )

                    mint_request.mark_executed(user=request.user, transaction=tx_record)

                    messages.success(
                        request,
                        f"Successfully minted {amount_tokens:,.6f} {yield_token.symbol} "
                        f"to {form.cleaned_data['recipient_name']} (tx: {tx_hash[:16]}...)",
                    )

                    return HttpResponseRedirect(reverse("admin:tokens_yieldtoken_change", args=[yield_token.pk]))

                except Exception as e:
                    mint_request.mark_failed(str(e))
                    messages.error(request, f"Minting failed: {e}")
                    return HttpResponseRedirect(reverse("admin:tokens_yieldtoken_change", args=[yield_token.pk]))
        else:
            form = MintForm()

        context = {
            **self.admin_site.each_context(request),
            "title": f"Mint {yield_token.symbol}",
            "subtitle": None,
            "yield_token": yield_token,
            "form": form,
            "opts": self.model._meta,
            "current_supply": total_supply_display,
            "is_minter": is_minter,
        }
        return render(request, "admin/tokens/yieldtoken/mint_form.html", context)


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

    def nav_change_display(self, obj):
        return f"${obj.old_nav_per_token} → ${obj.new_nav_per_token}"

    nav_change_display.short_description = "NAV Change"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
