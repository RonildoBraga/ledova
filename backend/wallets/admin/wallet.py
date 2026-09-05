from django.contrib import admin
from django.db.models import Count
from django.utils import timezone

from wallets.constants import WALLET_VERIFICATION_STATUS_VERIFIED
from wallets.models import Wallet


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = (
        "address_display",
        "name",
        "user_account",
        "chain",
        "holdings_count",
        "verification_status",
        "last_synced_at",
    )
    search_fields = (
        "name",
        "address",
        "user_account__user_profiles__user__email",
        "user_account__user_profiles__full_name",
        "chain",
    )
    list_filter = (
        "verification_status",
        "chain",
        "created_at",
        "verified_at",
        "last_synced_at",
    )
    readonly_fields = (
        "uuid",
        "holdings_count",
        "last_synced_at",
        "verified_at",
        "created_at",
        "updated_at",
        "address_index",
        "parent_public_key",
        "parent_chain_code",
        "parent_derivation_path",
    )
    actions = ["verify_wallets", "sync_holdings_action"]

    def get_queryset(self, request):

        return (
            super()
            .get_queryset(request)
            .select_related("user_account")
            .annotate(holdings_count=Count("holdings", distinct=True))
        )

    @admin.display(description="Address")
    def address_display(self, obj):
        return f"{obj.address[:10]}...{obj.address[-8:]}" if len(obj.address) > 18 else obj.address

    @admin.display(description="Holdings", ordering="holdings_count")
    def holdings_count(self, obj):
        return obj.holdings_count

    @admin.action(description="Mark selected wallets as verified (admin override)")
    def verify_wallets(self, request, queryset):
        updated = queryset.update(verification_status=WALLET_VERIFICATION_STATUS_VERIFIED, verified_at=timezone.now())
        self.message_user(request, f"{updated} wallets were verified.")

    @admin.action(description="Sync holdings from blockchain")
    def sync_holdings_action(self, request, queryset):
        from wallets.tasks import sync_wallet

        verified_wallets = queryset.filter(verification_status=WALLET_VERIFICATION_STATUS_VERIFIED)
        if not verified_wallets.exists():
            self.message_user(
                request, "No verified wallets selected. Only verified wallets can be synced.", level="warning"
            )
            return

        queued_count = 0
        for wallet in verified_wallets:
            sync_wallet.defer(wallet_uuid=str(wallet.uuid))
            queued_count += 1

        self.message_user(request, f"Queued sync for {queued_count} wallet(s). Balances will be updated shortly.")
