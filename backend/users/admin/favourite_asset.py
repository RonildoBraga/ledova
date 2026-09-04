from django.contrib import admin

from users.models.favourite_asset import FavouriteAsset


@admin.register(FavouriteAsset)
class FavouriteAssetAdmin(admin.ModelAdmin):
    list_display = ("uuid", "get_asset_symbol", "get_asset_name", "user_account", "created_at")
    list_display_links = ("uuid", "get_asset_symbol")
    search_fields = (
        "asset__symbol",
        "asset__name",
        "user_account__account_number",
        "user_account__user_profiles__user__email",
    )
    list_filter = ("asset__asset_type", "user_account", "created_at")
    readonly_fields = ("uuid", "created_at", "updated_at")
    autocomplete_fields = ("user_account", "asset")
    ordering = ("-created_at",)
    list_per_page = 25
    list_select_related = ("asset", "user_account")

    @admin.display(description="Asset Symbol", ordering="asset__symbol")
    def get_asset_symbol(self, obj):
        return obj.asset.symbol

    @admin.display(description="Asset Name", ordering="asset__name")
    def get_asset_name(self, obj):
        return obj.asset.name
