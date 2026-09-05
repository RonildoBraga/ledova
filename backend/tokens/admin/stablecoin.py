from django.contrib import admin
from django.utils import timezone

from tokens.models import Stablecoin
from tokens.services import mint_service

from ._helpers import action_buttons, bounded_chain_read, format_units
from .mintable_token import MintableTokenAdmin


@admin.register(Stablecoin)
class StablecoinAdmin(MintableTokenAdmin):
    mint_request_field = "stablecoin"
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
    readonly_fields = ["uuid", "total_supply_display", "reserve_updated_at", "created_at", "updated_at"]

    fieldsets = [
        (None, {"fields": ["uuid", "name", "symbol", "contract_address", "decimals", "is_active"]}),
        ("Blockchain Info", {"fields": ["total_supply_display"]}),
        ("Synthetic Reference Data", {"fields": ["reserve_amount", "reserve_updated_at"]}),
        ("Timestamps", {"fields": ["created_at", "updated_at"], "classes": ["collapse"]}),
    ]

    def save_model(self, request, obj, form, change):
        if change and "reserve_amount" in form.changed_data:
            obj.reserve_updated_at = timezone.now()
        super().save_model(request, obj, form, change)

    @admin.display(description="Total Supply")
    def total_supply_display(self, obj):
        if not obj.contract_address:
            return "-"
        raw_supply = bounded_chain_read(
            lambda: mint_service.token_service(obj).get_total_supply(),
            f"totalSupply() of {obj.symbol}",
        )
        if raw_supply is None:
            return "Unavailable"
        return f"${format_units(raw_supply, obj.decimals)}"

    @admin.display(description="Actions")
    def mint_action(self, obj):
        if not obj.is_active or not obj.contract_address:
            return "-"
        return action_buttons([("+ Mint", self.mint_url(obj), "#28a745")])
