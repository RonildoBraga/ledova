"""
Admin configuration for FavouriteAsset model.
"""

from django.contrib import admin

from users.models.favourite_asset import FavouriteAsset


@admin.register(FavouriteAsset)
class FavouriteAssetAdmin(admin.ModelAdmin):
    list_display = (
        "uuid",
        "get_asset_symbol",
        "get_asset_name",
        "user_account",
        "created_at",
    )
    list_display_links = ("uuid", "get_asset_symbol")
    search_fields = (
        "asset__symbol",
        "asset__name",
        "user_account__account_number",
        "user_account__user_profiles__user__email",
    )
    list_filter = (
        "asset__asset_type",
        "user_account",
        "created_at",
    )
    readonly_fields = ("uuid", "created_at", "updated_at")
    autocomplete_fields = ("user_account", "asset")
    ordering = ("-created_at",)
    list_per_page = 25
    fieldsets = (
        (None, {"fields": ("uuid", "user_account", "asset")}),
        (
            "System Information",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )
    actions = ["delete_selected_favourites"]

    def get_asset_symbol(self, obj):
        """Display the asset symbol."""
        return obj.asset.symbol

    get_asset_symbol.short_description = "Asset Symbol"
    get_asset_symbol.admin_order_field = "asset__symbol"

    def get_asset_name(self, obj):
        """Display the asset name."""
        return obj.asset.name

    get_asset_name.short_description = "Asset Name"
    get_asset_name.admin_order_field = "asset__name"

    @admin.action(description="Delete selected favourite assets")
    def delete_selected_favourites(self, request, queryset):
        deleted_count = queryset.count()
        queryset.delete()
        self.message_user(request, f"{deleted_count} favourite asset(s) deleted.")
