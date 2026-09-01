"""Reusable SQL for an isolated PostgreSQL tenant-policy proof.

Every tenant-scoped table gets the same policy shape: a row is visible (and
writable) only when its owning-account column is one of the account UUIDs in
the per-request session variable ``app.account_ids``. When the variable is
unset on a restricted, non-bypassing connection (for example, an
unauthenticated request or background job without tenant context),
``current_setting('app.account_ids', true)`` returns NULL and the predicate
matches nothing — i.e. the policy fails closed.

The proof role must be a NON-superuser, non-owner role for these policies to
take effect: PostgreSQL superusers and table owners bypass RLS. Importing this
module does not create roles, grants, policies, or session state.
"""

import re

GUC = "app.account_ids"

_SIMPLE_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")

_PREDICATE = "{col} = ANY (" "string_to_array(NULLIF(current_setting('app.account_ids', true), ''), ',')::uuid[]" ")"


def _validate_identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or _SIMPLE_IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{label} must be a simple lowercase PostgreSQL identifier")
    return value


def enable_policy_sql(table: str, owner_col: str, policy: str = "tenant_isolation") -> str:
    table = _validate_identifier(table, "table")
    owner_col = _validate_identifier(owner_col, "owner_col")
    policy = _validate_identifier(policy, "policy")
    predicate = _PREDICATE.format(col=owner_col)
    return (
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;\n"
        f"DROP POLICY IF EXISTS {policy} ON {table};\n"
        f"CREATE POLICY {policy} ON {table}\n"
        f"    USING ({predicate})\n"
        f"    WITH CHECK ({predicate});"
    )


def disable_policy_sql(table: str, policy: str = "tenant_isolation") -> str:
    table = _validate_identifier(table, "table")
    policy = _validate_identifier(policy, "policy")
    return f"DROP POLICY IF EXISTS {policy} ON {table};\n" f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;"


# Exact database table and owning-account column pairs used only by the
# isolated proof. Runtime activation and table expansion remain deferred.
CORE_TENANT_TABLES = [
    ("wallets", "user_account_id"),
    ("portfolios", "user_account_id"),
]
