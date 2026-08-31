from django.db import migrations

SUPPORTED_ASSET_SYMBOLS = ["BTC", "ETH", "USDC", "USDT", "AUDY", "AUSG"]

SPAM_ASSET_SYMBOLS = ["WL", "MEEP"]


def verify_supported_assets_and_cleanup_spam(apps, schema_editor):
    Asset = apps.get_model("assets", "Asset")
    Holding = apps.get_model("wallets", "Holding")
    HoldingSnapshot = apps.get_model("wallets", "HoldingSnapshot")

    updated = Asset.objects.filter(symbol__in=SUPPORTED_ASSET_SYMBOLS).update(is_verified=True)
    print(f"\n  Marked {updated} supported assets as verified")

    spam_holdings = Holding.objects.filter(asset__symbol__in=SPAM_ASSET_SYMBOLS)
    spam_count = spam_holdings.count()
    if spam_count:
        snapshot_count = HoldingSnapshot.objects.filter(holding__in=spam_holdings).delete()[0]
        spam_holdings.delete()
        print(f"  Deleted {spam_count} spam holdings and {snapshot_count} snapshots ({SPAM_ASSET_SYMBOLS})")

    dust_holdings = Holding.objects.filter(asset__is_verified=False, quantity=0)
    dust_count = dust_holdings.count()
    if dust_count:
        dust_snapshot_count = HoldingSnapshot.objects.filter(holding__in=dust_holdings).delete()[0]
        dust_holdings.delete()
        print(f"  Deleted {dust_count} zero-balance unverified holdings and {dust_snapshot_count} snapshots")

    deactivated = Asset.objects.filter(symbol__in=SPAM_ASSET_SYMBOLS).update(is_active=False)
    if deactivated:
        print(f"  Deactivated {deactivated} spam assets")


def reverse(apps, schema_editor):
    Asset = apps.get_model("assets", "Asset")
    Asset.objects.filter(symbol__in=SUPPORTED_ASSET_SYMBOLS).update(is_verified=False)
    Asset.objects.filter(symbol__in=SPAM_ASSET_SYMBOLS).update(is_active=True)


class Migration(migrations.Migration):

    dependencies = [
        ("assets", "0008_asset_is_verified"),
        ("wallets", "0004_wallet_is_operator"),
    ]

    operations = [
        migrations.RunPython(verify_supported_assets_and_cleanup_spam, reverse),
    ]
