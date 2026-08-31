import logging

from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from tokens.models import MintRequest, Stablecoin
from tokens.services import StablecoinService

logger = logging.getLogger(__name__)


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
        max_digits=12,
        decimal_places=2,
        min_value=0.01,
        label="Amount (AUD)",
        help_text="Amount in dollars (e.g., 100.00)",
    )

    deposit_reference = forms.CharField(
        max_length=100,
        label="Deposit Reference",
        help_text="Bank reference or transaction ID for the fiat deposit",
    )

    deposit_date = forms.DateField(
        label="Deposit Date",
        help_text="Date the fiat deposit was received",
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    notes = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        label="Notes (Optional)",
        help_text="Any additional notes about this mint request",
    )

    def clean_recipient_address(self):
        address = self.cleaned_data["recipient_address"]
        if not address.startswith("0x") or len(address) != 42:
            raise forms.ValidationError("Invalid Ethereum address format. Must be 42 characters starting with 0x.")
        return address

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        return int(amount * 100)


@admin.register(Stablecoin)
class StablecoinAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "symbol",
        "contract_address_short",
        "total_supply_display",
        "decimals",
        "is_active_badge",
        "mint_action",
        "created_at",
    ]
    list_filter = ["is_active", "decimals"]
    search_fields = ["name", "symbol", "contract_address"]
    readonly_fields = ["uuid", "total_supply_display", "reserve_updated_at", "created_at", "updated_at"]
    ordering = ["symbol"]

    fieldsets = [
        (
            None,
            {
                "fields": ["uuid", "name", "symbol", "contract_address", "decimals", "is_active"],
            },
        ),
        (
            "Blockchain Info",
            {
                "fields": ["total_supply_display"],
            },
        ),
        (
            "Synthetic Reference Data",
            {
                "fields": ["reserve_amount", "reserve_updated_at"],
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

    def save_model(self, request, obj, form, change):
        if change and "reserve_amount" in form.changed_data:
            from django.utils import timezone

            obj.reserve_updated_at = timezone.now()
        super().save_model(request, obj, form, change)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<uuid:uuid>/mint/",
                self.admin_site.admin_view(self.mint_view),
                name="tokens_stablecoin_mint",
            ),
        ]
        return custom_urls + urls

    def contract_address_short(self, obj):
        if obj.contract_address:
            return f"{obj.contract_address[:10]}...{obj.contract_address[-8:]}"
        return "-"

    contract_address_short.short_description = "Contract"

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

    def total_supply_display(self, obj):
        if not obj.contract_address:
            return "-"

        try:
            service = StablecoinService(contract_address=obj.contract_address)
            total_supply = service.get_total_supply()
            return f"${total_supply / 100:,.2f}"
        except Exception as e:
            logger.warning(f"Failed to get total supply for {obj.symbol}: {e}")
            return "Error"

    total_supply_display.short_description = "Total Supply"

    def mint_action(self, obj):
        if not obj.is_active or not obj.contract_address:
            return "-"

        mint_url = reverse("admin:tokens_stablecoin_mint", args=[obj.uuid])
        return format_html(
            '<a href="{}" style="display: inline-block; padding: 4px 10px; '
            "background-color: #28a745; color: white; text-decoration: none; "
            'border-radius: 4px; font-size: 11px; font-weight: bold;">+ Mint</a>',
            mint_url,
        )

    mint_action.short_description = "Actions"

    def mint_view(self, request, uuid):
        stablecoin = get_object_or_404(Stablecoin, uuid=uuid)

        if not stablecoin.is_active:
            messages.error(request, f"Cannot mint: {stablecoin.symbol} is not active")
            return HttpResponseRedirect(reverse("admin:tokens_stablecoin_change", args=[stablecoin.pk]))

        if not stablecoin.contract_address:
            messages.error(request, f"Cannot mint: {stablecoin.symbol} has no contract address")
            return HttpResponseRedirect(reverse("admin:tokens_stablecoin_change", args=[stablecoin.pk]))

        try:
            service = StablecoinService(contract_address=stablecoin.contract_address)
            current_supply = service.get_total_supply()
            current_supply_display = f"${current_supply / 100:,.2f}"
            is_minter = service.is_minter(service.signer_address)
        except Exception as e:
            logger.error(f"Failed to get stablecoin info: {e}")
            current_supply_display = "Error"
            is_minter = False

        if request.method == "POST":
            form = MintForm(request.POST)
            if form.is_valid():
                mint_request = MintRequest.objects.create(
                    stablecoin=stablecoin,
                    recipient_address=form.cleaned_data["recipient_address"],
                    recipient_name=form.cleaned_data["recipient_name"],
                    amount=form.cleaned_data["amount"],
                    deposit_reference=form.cleaned_data["deposit_reference"],
                    deposit_date=form.cleaned_data["deposit_date"],
                    notes=form.cleaned_data.get("notes", ""),
                    requested_by=request.user,
                )

                try:
                    tx_hash, tx_record = service.mint(
                        to_address=form.cleaned_data["recipient_address"],
                        amount=form.cleaned_data["amount"],
                        related_model="tokens.MintRequest",
                        related_uuid=str(mint_request.uuid),
                    )

                    mint_request.mark_executed(user=request.user, transaction=tx_record)

                    messages.success(
                        request,
                        f"Successfully minted {mint_request.amount_display} {stablecoin.symbol} "
                        f"to {form.cleaned_data['recipient_name']} (tx: {tx_hash[:16]}...)",
                    )

                    return HttpResponseRedirect(reverse("admin:tokens_mintrequest_change", args=[mint_request.pk]))

                except Exception as e:
                    mint_request.mark_failed(str(e))
                    messages.error(request, f"Minting failed: {e}")
                    return HttpResponseRedirect(reverse("admin:tokens_mintrequest_change", args=[mint_request.pk]))
        else:
            form = MintForm()

        context = {
            **self.admin_site.each_context(request),
            "title": f"Mint {stablecoin.symbol}",
            "subtitle": None,
            "stablecoin": stablecoin,
            "form": form,
            "opts": self.model._meta,
            "current_supply": current_supply_display,
            "is_minter": is_minter,
        }
        return render(request, "admin/tokens/stablecoin/mint_form.html", context)
