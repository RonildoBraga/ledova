SYSTEM_WIDE = {
    "assets.sync_all_assets": "Refreshes the global asset catalogue, which belongs to no tenant.",
    "assets.sync_exchange_rates": "Fetches published rates, identical for every tenant.",
    "blockchain.tasks.check_pending_transactions": "Polls the chain for every broadcast this deployment made, "
    "keyed by transaction hash rather than by anyone who owns one.",
    "blockchain.tasks.cleanup_failed_transactions": "Retires rows the chain has refused, across all of them.",
    "compliance.tasks.run_batch_monitoring": "Screens every account against the operator's rules, which is "
    "the operator's question rather than any customer's.",
    "compliance.tasks.check_periodic_reviews": "Finds which reviews are due across every account.",
    "offerings.tasks.subscription.reconcile_subscriptions": "Matching a bank line means searching every tenant's "
    "subscriptions, because the line does not say whose it is.",
    "offerings.tasks.subscription.expire_unpaid_subscriptions": "Sweeps every offering's unpaid\n"
    "subscriptions on a clock, across all of them.",
    "shared.tasks.orphaned_files.sweep_private_uploads": "Compares the whole object store against the whole "
    "database, so it has to see both in full.",
    "tokens.tasks.deployment.check_pending_token_deployments": "Polls every deployment this operator started.",
    "tokens.tasks.review_request.check_executing_issuance_requests": "Polls every issuance the relayer claimed.",
    "tokens.tasks.signing_challenge.purge_signing_challenges": "Deletes expired challenges regardless of whose.",
    "tokens.tasks.swap_reconciler.resolve_executing_swaps": "Asks the chain about every swap left executing, "
    "and a swap has two parties, so neither one's principal would cover it.",
    "users.tasks.retention.purge_classification_evidence": "Applies the retention clock across every account.",
    "wallets.tasks.sync.sync_all_wallets": "Fans out over every wallet; the per-wallet task it defers is the "
    "one that acts for somebody.",
    "wallets.tasks.confirmation.check_all_pending_transactions": "Fans out over every pending transaction.",
    "wallets.tasks.confirmation.cleanup_stale_pending_transactions": "Retires stale rows across all accounts.",
    "whitelist.tasks.sync.sync_all_entries": "Reconciles the on-chain whitelist, which is one list for the "
    "whole deployment and is staff-only in the API for the same reason.",
    "whitelist.tasks.sync.reconcile_failed_adds": "Asks the chain about every entry recorded failed with a hash "
    "it sent, which is a question about the deployment's one whitelist rather than about whoever owns any "
    "wallet on it.",
    "procrastinate.builtin_tasks.remove_old_jobs": "Procrastinate's own queue maintenance.",
    "builtin:procrastinate.builtin_tasks.remove_old_jobs": "The same task under its builtin alias.",
}

PRINCIPAL_BEARING = {
    "offerings.tasks.subscription.allot_subscription_task": "Allots shares for one investor's "
    "subscription, on the money "
    "path: it writes that investor's rows and nobody else's.",
    "tokens.tasks.deployment.deploy_share_token_task": "Deploys one issuer's token and writes back to it.",
    "tokens.tasks.review_request.execute_review_request_task": "Executes one issuer's issuance request, on the "
    "money path, and records the issuance against it.",
    "wallets.tasks.confirmation.confirm_pending_transaction": "Confirms one wallet's transaction and moves the "
    "balance it belongs to, on the money path. Converted: its principal is a required argument, the "
    "request that broadcast the transfer passes its user, and the Alchemy webhook and the "
    "check_all_pending_transactions sweep pass None because no user caused those runs. The principal is "
    "captured at enqueue and used at run, and that gap grows with the delay: the second confirmation check "
    "is scheduled 120 seconds out, and a principal who left the account in between resolves no wallet and "
    'the task answers "Wallet not found" - fails closed and quiet, with the sweep finishing the row as '
    "the operator. The design covers it; the sentence exists so the next conversion with a longer delay "
    "knows the gap is proportional to it.",
    "wallets.tasks.sync.sync_wallet": "Reads and writes the holdings of exactly one wallet.",
    "documents.tasks.extract.extract_document": "Reads one uploader's document and writes an extraction " "against it.",
    "users.tasks.notifications.send_push_notification": "Sends to one user's device tokens.",
    "users.tasks.notifications.send_transaction_notification": "Sends to one user about one transaction.",
}

OPERATOR_READS = {
    "users.services.accounts.account_members": "R15, and the first catalogue entry whose boundary is a "
    "function rather than a table: what makes it safe is not the operator connection but the account it is "
    "handed. transaction_confirmation.py:168 passes tx.wallet.user_account, from a wallet the task already "
    "resolved under its own principal, so a caller cannot ask for an account it could not reach. A future "
    "caller that took the account from a request body would break that without touching this function. "
    "Deciding who to tell about an account's transaction is "
    "an account-level question, and users_userprofile's policy answers a user-level one - scoped, the "
    "notification reaches only the member who acted. Measured: as the owner two members, as the app role "
    "one. The helper runs on the operator connection, takes the account as its only input, and filters to "
    "that account's members itself, so BYPASSRLS cannot return anyone else. Widening the profile policy "
    "instead would change what UserProfile.visible_to_user means everywhere to fix one service.",
}

READS_MUST_SURVIVE_THE_POLICIES = {
    "wallets.tasks.sync.sync_wallet": "Omarch 2's #319 gives this one a trap worth stating before anyone "
    "converts it. _share_balance reads tokens_sharetoken through the ORM, and under a company-owner policy "
    "an investor owns no issuer company, so a scoped sync_wallet would find no share class and stop syncing "
    "share holdings silently - the failure path returns None and logs. Nothing breaks today only because "
    "every task runs on the operator alias. It resolves when tokens/0024's leaf policy carries the market "
    "term, since a deployed token is then visible to an investor principal.",
}

CLASSIFIED = {**SYSTEM_WIDE, **PRINCIPAL_BEARING}
