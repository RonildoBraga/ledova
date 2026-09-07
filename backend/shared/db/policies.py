PRINCIPAL = "current_setting('app.user_id')::bigint"

MEMBER_ACCOUNTS = "app_member_account_ids"
VISIBLE_COMPANIES = "app_visible_company_ids"
MANAGEABLE_COMPANIES = "app_manageable_company_ids"

HELPERS = {
    MEMBER_ACCOUNTS: f"""
        SELECT membership.useraccount_id
          FROM customer_accounts_account_user_profiles membership
          JOIN users_userprofile profile ON profile.uuid = membership.userprofile_id
         WHERE profile.user_id = {PRINCIPAL}
    """,
    VISIBLE_COMPANIES: f"SELECT uuid FROM companies_company WHERE owner_id = {PRINCIPAL}",
    MANAGEABLE_COMPANIES: f"SELECT uuid FROM companies_company WHERE owner_id = {PRINCIPAL}",
}

LEAF_TABLES = ("companies_company", "users_userprofile", "customer_accounts_account_user_profiles")


def _member(column):
    return f"{column} IN (SELECT {MEMBER_ACCOUNTS}())"


def _company(column, helper):
    return f"{column} IN (SELECT {helper}())"


OWNERSHIP_BOUND = (
    "EXISTS (SELECT 1 FROM wallets held "
    "WHERE held.uuid = tokens_transferorder.wallet_id "
    "AND held.user_account_id = tokens_transferorder.owner_account_id "
    "AND lower(held.address) = lower(tokens_transferorder.wallet_address))"
)

POLICIES = {
    "companies_company": (f"owner_id = {PRINCIPAL}", f"owner_id = {PRINCIPAL}"),
    "users_userprofile": (f"user_id = {PRINCIPAL}", f"user_id = {PRINCIPAL}"),
    "customer_accounts_account_user_profiles": (
        f"userprofile_id IN (SELECT uuid FROM users_userprofile WHERE user_id = {PRINCIPAL})",
        f"userprofile_id IN (SELECT uuid FROM users_userprofile WHERE user_id = {PRINCIPAL})",
    ),
    "documents": (f"uploaded_by_id = {PRINCIPAL}", f"uploaded_by_id = {PRINCIPAL}"),
    "users_device_token": (f"user_id = {PRINCIPAL}", f"user_id = {PRINCIPAL}"),
    "notifications": (f"user_id = {PRINCIPAL}", f"user_id = {PRINCIPAL}"),
    "users_financialprofile": (f"user_id = {PRINCIPAL}", f"user_id = {PRINCIPAL}"),
    "users_notification_preferences": (f"user_id = {PRINCIPAL}", f"user_id = {PRINCIPAL}"),
    "users_userpreferences": (f"user_id = {PRINCIPAL}", f"user_id = {PRINCIPAL}"),
    "customer_accounts_account": (_member("uuid"), _member("uuid")),
    "wallets": (_member("user_account_id"), _member("user_account_id")),
    "transactions": (_member("user_account_id"), _member("user_account_id")),
    "portfolios": (_member("user_account_id"), _member("user_account_id")),
    "favourite_assets": (_member("user_account_id"), _member("user_account_id")),
    "users_investorclassification": (_member("user_account_id"), _member("user_account_id")),
    "offerings_subscription": (_member("user_account_id"), _member("user_account_id")),
    "tokens_transferorder": (
        f"{_member('owner_account_id')} AND {OWNERSHIP_BOUND}",
        f"{_member('owner_account_id')} AND {OWNERSHIP_BOUND}",
    ),
    "companies_companydocument": (
        _company("company_id", VISIBLE_COMPANIES),
        _company("company_id", MANAGEABLE_COMPANIES),
    ),
    "tokens_sharetoken": (
        _company("company_id", VISIBLE_COMPANIES),
        _company("company_id", MANAGEABLE_COMPANIES),
    ),
    "offerings_offering": (
        _company("company_id", VISIBLE_COMPANIES),
        _company("company_id", MANAGEABLE_COMPANIES),
    ),
}

AWAITING_R0 = {
    "tokens_capitalincreaserequest": (
        "Reaches its company through token -> company and has no company_id yet. The tokens R0 lane "
        "adds the column; until it lands there is nothing for a policy to compare."
    ),
    "tokens_shareissuancerequest": (
        "Reaches its company through token -> company and has no company_id yet. Same lane, same column, "
        "and the same reason it cannot be written early."
    ),
    "tokens_swaporder": (
        "Needs seller_wallet_id and buyer_wallet_id rather than account ids, because only a VERIFIED "
        "wallet confers sight of a swap and verification changes after the row is written."
    ),
}

FRAMEWORK = {
    "auth_group": "Django's own permission grouping.",
    "auth_permission": "Django's own permission rows, one per model and action.",
    "authentication_customuser": "The user table itself. A principal is a row here, so scoping it by the "
    "principal would make authentication depend on the answer it is trying to produce.",
    "django_admin_log": "The admin's audit trail, written and read on the operator connection only.",
    "django_content_type": "Django's model registry.",
    "django_session": "Session rows, read before any view runs and keyed by a cookie rather than a user.",
    "token_blacklist_outstandingtoken": "Issued refresh tokens, read during authentication, before a "
    "principal exists.",
    "token_blacklist_blacklistedtoken": "Revoked refresh tokens, read during authentication for the same reason.",
    "procrastinate_jobs": "The worker queue, which runs on the operator connection and has no acting user.",
    "procrastinate_events": "Worker job history, written by the queue on the operator connection.",
    "procrastinate_periodic_defers": "Worker schedule bookkeeping, with no tenant in it at all.",
    "procrastinate_workers": "Worker registration rows, one per running worker process.",
    "auth_group_permissions": "Django's own permission plumbing, joining a group to a permission.",
    "authentication_customuser_groups": "Django's own permission plumbing, joining a user to a group.",
    "authentication_customuser_user_permissions": "Django's own permission plumbing, per-user grants.",
}

OPERATOR_ONLY = {
    "compliance_compliancealert": "Raised and worked by compliance staff on the operator connection. It "
    "carries user_account_id but no queryset scopes it, so a policy would be a new rule rather than a "
    "translation of one.",
    "compliance_customerriskassessment": "Same surface, same connection, same reason.",
    "compliance_transactionscreening": "Same surface, same connection, same reason.",
    "compliance_alertproceduretemplate": "Operator-authored procedure text, the same for every tenant.",
    "compliance_alertprocedurestep": "A step of that operator-authored text, reached through its template.",
    "compliance_alertchecklistitem": "A checklist item raised against an alert, reached through it.",
    "compliance_monitoringrule": "Operator-authored screening rules, the same for every tenant.",
    "blockchain_blockchaintransaction": "A record of what the relayer broadcast, written by workers and "
    "keyed by transaction hash rather than by any tenant.",
    "tokens_mintrequest": "Written on the relayer path by workers, reached through its token.",
    "tokens_navupdate": "Issuer-published NAV history, reached through its token.",
    "tokens_ordermodificationlog": "An audit row reached through the order it modified.",
    "tokens_shareissuance": "The executed half of an issuance request, reached through it.",
    "tokens_yieldtoken": "Token configuration reached through its share token.",
}

NOT_TENANCY = {
    "assets_asset": "A global catalogue. visible_to_user returns self, which is a shape rather than a scope.",
    "feature_flags": "A kill switch wearing a tenancy method's name: visible_to_user filters on enabled.",
    "whitelist_whitelistentry": "Staff-only, which is authorisation rather than tenancy, and stays in code.",
    "signing_challenges": "Reached by address through a service rather than by any queryset; #256 deleted "
    "the two methods that looked like scoping. The tokens R0 lane decides its column.",
    "holdings": "Reached only through its wallet, which is scoped, and carries no tenant column of its own.",
    "asset_chain_deployments": "Part of the asset catalogue.",
    "asset_snapshots": "Price history for the catalogue, identical for every tenant.",
    "assets_exchangerate": "Published rates, identical for every tenant.",
    "holding_snapshots": "Portfolio history reached through its holding, which is reached through a wallet.",
    "document_extractions": "Reached through its document, which is scoped by uploaded_by.",
    "shared_country": "A reference list of countries, identical for every tenant.",
    "operators_operator": "A singleton naming the operator of this deployment.",
    "operators_operator_supported_settlement_assets": "Which assets that singleton settles in.",
    "offerings_offering_documents": "A link row reached only through its offering, which is scoped. Nothing "
    "scopes this table today, so a policy here would be a new rule rather than a translation of one - and it "
    "is worth writing the day anything reaches these rows without going through the offering first.",
    "offerings_offering_settlement_assets": "A link row from a scoped offering to the global asset catalogue, "
    "reached only through the offering, and carrying nothing the catalogue does not already publish.",
    "portfolios_wallets": "A link row between a scoped portfolio and a scoped wallet, reached through either, "
    "and revealing nothing that reading both of those tables would not.",
}

UNSCOPED = {**FRAMEWORK, **OPERATOR_ONLY, **NOT_TENANCY}
