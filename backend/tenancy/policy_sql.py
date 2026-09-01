"""Reusable SQL for PostgreSQL row-level-security tenant policies.

Every tenant-scoped table gets the same policy shape: a row is visible (and
writable) only when its owning-account column is one of the account UUIDs in
the per-request session variable ``app.account_ids``. When the variable is
unset (background jobs connecting as a bypassing role, or an unauthenticated
request), ``current_setting('app.account_ids', true)`` returns NULL and the
predicate matches nothing — i.e. the policy fails closed.

The app must connect as a NON-superuser, non-owner role for these policies to
take effect: PostgreSQL superusers and table owners bypass RLS.
"""

GUC = "app.account_ids"

_PREDICATE = (
    "{col} = ANY (string_to_array(current_setting('app.account_ids', true), ',')::uuid[])"
)


def enable_policy_sql(table: str, owner_col: str, policy: str = "tenant_isolation") -> str:
    predicate = _PREDICATE.format(col=owner_col)
    return (
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;\n"
        f"DROP POLICY IF EXISTS {policy} ON {table};\n"
        f"CREATE POLICY {policy} ON {table}\n"
        f"    USING ({predicate})\n"
        f"    WITH CHECK ({predicate});"
    )


def disable_policy_sql(table: str, policy: str = "tenant_isolation") -> str:
    return (
        f"DROP POLICY IF EXISTS {policy} ON {table};\n"
        f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;"
    )


# (table, owning-account column) for tables that already carry a direct
# UserAccount FK. New tenant tables are added here as they gain an account
# column; see docs/adr/0002-rls-tenant-isolation.md for the rollout.
CORE_TENANT_TABLES = [
    ("wallets", "user_account_id"),
    ("portfolios", "user_account_id"),
]
