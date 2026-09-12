from django.db import migrations

from shared.db.policy_sql import grant_reachable_tables


def grant(apps, schema_editor):
    grant_reachable_tables(schema_editor)


class Migration(migrations.Migration):

    dependencies = [
        ("shared", "0007_review_request_policies"),
        ("users", "0021_trigger_types_from_the_column"),
        ("tokens", "0040_swap_parent_identity"),
        ("wallets", "0019_chain_observations"),
        ("companies", "0008_company_registry_verification"),
        ("offerings", "0006_trigger_follows_and_refuses"),
        ("documents", "0003_documentread_document_attached_at_and_more"),
        ("blockchain", "0006_signer_admission"),
        ("compliance", "0005_remove_fiat_transaction_and_high_risk_country"),
        ("assets", "0014_native_chain_deployments"),
        ("portfolios", "0005_delete_portfoliosnapshot"),
        ("whitelist", "0004_failure_reconciled_at"),
        ("feature_flags", "0002_add_trading_enabled_flag"),
        ("operators", "0001_initial"),
        ("authentication", "0009_otp_attempts_drop_unused_columns"),
        ("token_blacklist", "0013_alter_blacklistedtoken_options_and_more"),
        ("admin", "0003_logentry_add_action_flag_choices"),
        ("sessions", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [migrations.RunPython(grant, migrations.RunPython.noop)]
