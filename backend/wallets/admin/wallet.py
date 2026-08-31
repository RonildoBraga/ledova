from django.contrib import admin
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
        "custody_model",
        "verification_status",
        "is_whitelisted_for_securities",
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
        "custody_model",
        "is_whitelisted_for_securities",
        "chain",
        "created_at",
        "verified_at",
        "last_synced_at",
    )
    readonly_fields = (
        "uuid",
        "custody_model",
        "holdings_count",
        "last_synced_at",
        "last_synced_block",
        "verified_at",
        "whitelisted_at",
        "reconstruction_status",
        "reconstruction_complete",
        "reconstruction_completed_at",
        "created_at",
        "updated_at",
        # HD wallet fields (set programmatically from hardware wallet import)
        "address_index",
        "parent_public_key",
        "parent_chain_code",
        "parent_derivation_path",
    )
    fieldsets = (
        (
            "Wallet Information",
            {
                "fields": (
                    "uuid",
                    "user_account",
                    "name",
                    "address",
                    "chain",
                    "custody_model",
                )
            },
        ),
        (
            "Hardware Wallet (Optional)",
            {
                "fields": (
                    "derivation_path",
                    "master_fingerprint",
                    "address_index",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "HD Wallet Parent Key (for deriving additional addresses)",
            {
                "fields": (
                    "parent_public_key",
                    "parent_chain_code",
                    "parent_derivation_path",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Verification",
            {
                "fields": (
                    "verification_status",
                    "verification_challenge",
                    "verification_signature",
                    "verified_at",
                )
            },
        ),
        (
            "Securities Whitelisting",
            {
                "fields": (
                    "is_whitelisted_for_securities",
                    "whitelisted_at",
                    "whitelisting_authority",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Holdings & Sync",
            {
                "fields": (
                    "holdings_count",
                    "last_synced_at",
                    "last_synced_block",
                )
            },
        ),
        (
            "Reconstruction",
            {
                "fields": (
                    "reconstruction_status",
                    "reconstruction_complete",
                    "reconstruction_completed_at",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "System Information",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("user_account")

    actions = ["verify_wallets", "sync_holdings_action"]

    def address_display(self, obj):
        return f"{obj.address[:10]}...{obj.address[-8:]}" if len(obj.address) > 18 else obj.address

    address_display.short_description = "Address"

    def holdings_count(self, obj):
        return obj.holdings.count()

    holdings_count.short_description = "Holdings"

    def verify_wallets(self, request, queryset):
        updated = queryset.update(verification_status=WALLET_VERIFICATION_STATUS_VERIFIED, verified_at=timezone.now())
        self.message_user(request, f"{updated} wallets were verified.")

    verify_wallets.short_description = "Mark selected wallets as verified (admin override)"

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

    sync_holdings_action.short_description = "Sync holdings from blockchain"
