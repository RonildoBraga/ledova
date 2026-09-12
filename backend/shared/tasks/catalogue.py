from typing import Literal, NamedTuple


class TaskConversion(NamedTuple):
    status: Literal["pending", "converted"]
    converted_pr: int | None = None
    waiting_reason: str = ""


SYSTEM_WIDE = {
    "assets.sync_all_assets": "Refreshes the global asset catalogue, which belongs to no tenant.",
    "assets.sync_exchange_rates": "Fetches published rates, identical for every tenant.",
    "blockchain.tasks.check_pending_transactions": "Polls recorded hashes of this deployment's pending and "
    "submitted transactions, across all issuers.",
    "blockchain.tasks.cleanup_failed_transactions": "Reports overdue unresolved rows across the deployment "
    "for queued legacy jobs; receipt recovery runs in check_pending_transactions.",
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
    "tokens.tasks.former_holders.fold_every_share_class": "Reads the Transfer log of every deployed "
    "share class and writes the cessations it finds. It is the deployment's statutory register rather "
    "than any owner's data, and R24 makes the table operator-written for that reason.",
    "tokens.tasks.former_holders.purge_former_members_past_the_clock": "Deletes former-member records "
    "seven years after the date they ceased, which is the only deletion anyone may perform on that "
    "table - the app role's policy refuses all three write commands.",
    "tokens.tasks.signing_challenge.purge_signing_challenges": "Deletes expired challenges regardless of whose.",
    "tokens.tasks.swap_expiry.expire_unclaimed_matches": "Releases eligible unclaimed expired matches across both "
    "parties, retaining every swap with a transaction claim or uncertain history.",
    "tokens.tasks.swap_reconciler.resolve_executing_swaps": "Asks the chain about every swap left executing, "
    "and a swap has two parties, so neither one's principal would cover it.",
    "users.tasks.retention.purge_classification_evidence": "Applies the retention clock across every account.",
    "documents.tasks.retention.purge_document_evidence": "Purges expired supporting and unattached payslips "
    "across all uploaders on the operator connection, without a requesting user.",
    "wallets.tasks.chain_observations.observe_wallet_chains": "Polls the chain for every submission whose "
    "watch is due, across all accounts. The chain answers about a transaction, not about whose it is.",
    "wallets.tasks.submissions.recover_wallet_submissions": "Retries every submission left pending across all "
    "accounts on a clock; the owner is not present and each retry re-reads its own row.",
    "wallets.tasks.sync.sync_all_wallets": "Fans out over every wallet; the per-wallet task it defers is the "
    "one that acts for somebody.",
    "wallets.tasks.confirmation.check_all_pending_transactions": "Requeues pending transactions and unfinished "
    "balance reconciliation across all accounts.",
    "wallets.tasks.confirmation.cleanup_stale_pending_transactions": "Reports overdue pending rows across all "
    "accounts for queued legacy jobs without changing status or balances.",
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
    "subscription, on the money path: it executes the issuer's issuance request, seeds the recipient's "
    "holding and marks the investor's subscription allotted.",
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
    "documents.tasks.extract.extract_document": "Reads one uploader's document and writes an "
    "extraction against it. Converted: the principal is a required argument with no default, the "
    "upload passes its uploader and the staff rerun passes None, because a re-extraction is the "
    "operator's action and reaches documents no single customer owns. The whole body runs inside "
    "that context, which is what puts ExtractionService's three retention rechecks - the initial "
    "locked check, the bytes read and the save - on the alias the enqueue chose, around an "
    "external call no transaction can be held across.",
    "users.tasks.notifications.send_push_notification": "Sends to one user's device tokens. Converted: "
    "the required user_id was already the recipient principal, so the enqueue payload is unchanged and "
    "the whole body - lookup, preferences, inbox insert, device read and invalid-device deactivation - "
    "runs inside acting_for that recipient. A None recipient is refused rather than run as the operator, "
    "because acting_for(None) means operator and nothing in the payload would say that was unintended.",
    "users.tasks.notifications.send_transaction_notification": "Sends to one user about one transaction. "
    "Converted the same way, and the transaction lookup moved inside the recipient context, so a "
    "transaction the recipient cannot reach is refused instead of described to them. The gap between "
    "enqueue and run is up to four attempts at sixty seconds: _notify_wallet_users fans out one job per "
    "account member on the operator connection, and a member removed in between resolves no transaction "
    'and answers "Transaction not found" while the remaining members are notified normally.',
}

CONVERSIONS = {
    "offerings.tasks.subscription.allot_subscription_task": TaskConversion(
        status="pending",
        waiting_reason="allot and retry_allotment enqueue the subscription UUID and executed_by, which is "
        "the approving operator's audit identity, not a scoped investor principal. Execution crosses two "
        "write scopes: offerings_subscription is member-written, while tokens_shareissuancerequest is "
        "issuer-written. The subscriber can now read the linked request but still cannot execute its "
        "writes. Conversion needs explicit principal capture and separate bounded issuance and investor "
        "steps, including the recipient holding and final subscription update; one acting_for block "
        "cannot cover an investor subscribing to another issuer.",
    ),
    "tokens.tasks.deployment.deploy_share_token_task": TaskConversion(
        status="pending",
        waiting_reason="ShareTokenService.start_deployment and retry_deployment enqueue only token_uuid "
        "from issuer API and staff admin paths. The worker never selects a principal. Conversion must "
        "carry the issuer principal or an explicit operator choice from those producers and prove "
        "deployment, retry and recovery writes under tokens_sharetoken's company-owner write policy. "
        "The owner column and public operator-wallet read policies already exist; they are not pending "
        "migration blockers.",
    ),
    "tokens.tasks.review_request.execute_review_request_task": TaskConversion(
        status="pending",
        waiting_reason="ReviewWorkflowAdmin.execute_view passes the staff actor as executed_by for audit "
        "without selecting a database principal. CapitalIncreaseRequest and ShareIssuanceRequest writes "
        "require the issuer's company owner. Share issuance also calls _seed_recipient_holding, which "
        "joins and locks the recipient wallet; an issuer principal cannot reach an unrelated investor's "
        "private wallet. Conversion needs an explicit enqueue principal/operator choice and a bounded "
        "recipient-holding step before the issuer work can run scoped without dropping that side effect.",
    ),
    "wallets.tasks.confirmation.confirm_pending_transaction": TaskConversion(status="converted", converted_pr=327),
    "wallets.tasks.sync.sync_wallet": TaskConversion(
        status="pending",
        waiting_reason="Verification, the wallet admin, the Alchemy webhook and sync_all_wallets all "
        "enqueue only wallet_uuid. The worker never selects a principal for its wallet and transaction "
        "writes. Conversion must preserve the verifying user's principal, make the admin/webhook/sweep "
        "operator choices explicit, and test membership lost between enqueue and execution. The deployed "
        "share-token read prerequisite is already resolved, as recorded in READS_MUST_SURVIVE_THE_POLICIES; "
        "it is not a reason to wait for tokens/0024.",
    ),
    "documents.tasks.extract.extract_document": TaskConversion(status="converted", converted_pr=525),
    "users.tasks.notifications.send_push_notification": TaskConversion(status="converted", converted_pr=523),
    "users.tasks.notifications.send_transaction_notification": TaskConversion(status="converted", converted_pr=523),
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
    "wallets.tasks.sync.sync_wallet": "Resolved prerequisite to retain during conversion: "
    "tokens/0024_r0_sharetoken_owner already supplies non-null owner_id, and POLICIES now gives "
    "tokens_sharetoken an owner OR deployed-with-contract market SELECT term. "
    "wallets.services.chain._share_balance uses deployed_at, so its share class is visible to an investor "
    "without issuer ownership. Removing the market term would make that lookup return None and leave "
    "the share holding unsynced. The remaining work is principal capture and scoped execution, recorded "
    "in CONVERSIONS, rather than a missing migration or token-read policy.",
}

CLASSIFIED = {**SYSTEM_WIDE, **PRINCIPAL_BEARING}
