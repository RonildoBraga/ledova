"""Provision the RLS app role and enable policies on the core tenant tables.

Inert while the application connects as the database owner/superuser (owners
and superusers bypass RLS). Enforcement activates when the web process is
switched to connect as the non-superuser ``app_user`` role (see
docs/adr/0002-rls-tenant-isolation.md, Phase 2).
"""

from django.db import migrations

from tenancy.policy_sql import CORE_TENANT_TABLES, enable_policy_sql, disable_policy_sql

APP_ROLE = "app_user"

CREATE_ROLE = f"""
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
        CREATE ROLE {APP_ROLE} NOLOGIN;
    END IF;
END
$$;
GRANT USAGE ON SCHEMA public TO {APP_ROLE};
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE};
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE};
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE};
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE};
"""

DROP_ROLE_GRANTS = f"""
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {APP_ROLE};
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {APP_ROLE};
REVOKE USAGE ON SCHEMA public FROM {APP_ROLE};
"""

_enable = "\n".join(enable_policy_sql(t, col) for t, col in CORE_TENANT_TABLES)
_disable = "\n".join(disable_policy_sql(t) for t, _ in CORE_TENANT_TABLES)


class Migration(migrations.Migration):
    dependencies = [
        ("wallets", "0004_wallet_is_operator"),
        ("portfolios", "0003_remove_portfolio_template_and_target_asset_allocation"),
    ]

    operations = [
        migrations.RunSQL(CREATE_ROLE, reverse_sql=DROP_ROLE_GRANTS),
        migrations.RunSQL(_enable, reverse_sql=_disable),
    ]
