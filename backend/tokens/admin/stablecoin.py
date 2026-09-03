import logging

from django.contrib import admin
from django.utils import timezone

from tokens.models import Stablecoin
from tokens.services import mint_service

from ._helpers import action_buttons, format_units
from .mintable_token import MintableTokenAdmin

logger = logging.getLogger(__name__)


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
        try:
            return f"${format_units(mint_service.token_service(obj).get_total_supply(), obj.decimals)}"
        except Exception as exc:
            logger.warning(f"Failed to get total supply for {obj.symbol}: {exc}")
            return "Error"

    @admin.display(description="Actions")
    def mint_action(self, obj):
        if not obj.is_active or not obj.contract_address:
            return "-"
        return action_buttons([("+ Mint", self.mint_url(obj), "#28a745")])
