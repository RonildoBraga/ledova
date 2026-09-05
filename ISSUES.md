# Deferred high-risk work

This document records known high-risk work intentionally deferred from the
experimental local/testnet release. Open areas require implementation, tests,
and independent review before any public multi-user or real-value use. Each
item names where it lives in the code today.

1. **Tenant isolation and authorization — completed 2026-09-02.** Customer
   queries and mutations are self-scoped through the `visible_to_user` /
   `manageable_by_user` querysets (owner FKs are NOT NULL), every detail
   route, custom action, operator route and collection route is covered by
   `backend/shared/tests/test_cross_tenant_routes.py`, and global operator
   routes require `IsAdminUser`. PostgreSQL RLS is not planned.
2. **Authentication hardening — completed 2026-09-05.** Refresh rotation and
   blacklist (`authentication/services/tokens.py`), hashed expiring
   attempt-capped OTP (`authentication/services/email_codes.py`), per-email
   throttle, no DEBUG bypass, cookie flags from `settings.AUTH_COOKIE`, and
   CSRF on the cookie transport: `HybridJWTAuthentication` runs DRF's
   `CSRFCheck` for cookie-sourced POST/PUT/PATCH/DELETE (403 `CSRF Failed`),
   Bearer requests skip it and win over an `access` cookie sent beside them
   (React Native's cookie jar replays it), `auth/verify`, sign-in and email
   verification issue
   the readable `csrftoken` cookie (scoped like the auth cookies), and the
   dashboard's axios client echoes it as `X-CSRFToken` and replays once after a
   CSRF 403 (`authentication/tests/test_csrf.py`,
   `dashboard/src/services/apiClient.ts`).
3. **SSE query JWTs — completed 2026-09-05.** The trading event stream
   (`backend/tokens/views/trading_events.py`) authenticates only through
   `HybridJWTAuthentication`: the `access` cookie for the dashboard
   `EventSource` (`withCredentials`) and the `Authorization: Bearer` header
   for mobile (`react-native-sse` `headers` option). A JWT in the `?auth=`
   query string is ignored and the request is rejected exactly like an
   anonymous one (`tokens/tests/test_trading_events_authorization.py`), so
   proxies, browser history and logs never see a token.
4. **Signed-intent binding and replay.** `tokens/services/atomic_swap_service.py`
   signs a nonce and deadline per swap, but order create/cancel/modify messages
   (`tokens/services/trading_order_service.py`,
   `order_modification_service.py`) are not bound to one reviewed action,
   account, chain, contract, amount, recipient and short expiry, and a
   challenge is not consumed exactly once.
5. **Trading concurrency and idempotency.** `select_for_update` covers matching
   (`tokens/services/transfer_service.py`) and modification, but there are no
   state-machine invariants at the database level, no replay protection and no
   idempotency keys around order and swap creation, cancellation, matching and
   settlement.
6. **On-chain and background-job idempotency.** Share-token deployment and
   issuance are covered since 2026-09-05: a deployment re-run adopts the
   factory's address for the token identifier (`<acn>:<symbol>`), a sent
   create transaction never returns the token to draft (the admin "Retry
   Deployment" button re-queues a stuck one), issuance is refused before any
   transaction when the recipient is not whitelisted, the cap is exceeded or
   the token is paused, a capital increase is refused unless its total is above
   the cap the chain holds now and increases are serialised per token with a
   row lock on the `ShareToken` (a second executor reads the cap only after the
   first has mined and committed; the request status is re-read under that
   lock so a stale copy of a finished request is refused), a request is
   claimed with a compare-and-set on its status so two Execute submits cannot
   both mint, the mint hash is
   written to the request's `ShareIssuance` (`idempotency_key`
   `issuance-request:<uuid>`) and the `setAuthorizedShares` hash to a
   `BlockchainTransaction` for the `CapitalIncreaseRequest` before the receipt
   is awaited, so a retry after a lost receipt completes from that hash instead
   of sending again (a reverted call is forgotten and re-sent),
   `check_executing_issuance_requests` (every
   5 minutes) finishes an issuance or capital increase a killed worker left
   `EXECUTING` after the call was sent, pause and unpause read `paused()` and
   reconcile the DB
   status when the chain already holds the target state, and `make chain-test`
   proves the flow against a real Hardhat node
   (`tokens/tests/test_chain_integration.py`, on SQLite and on PostgreSQL in
   CI). Still open: minting
   (`tokens/services/mint_service.py`), the whitelist service
   (`whitelist/services/whitelist.py`), a request left `EXECUTING` before its
   mint was sent (nothing recorded to resume on; the sweep only logs it), a
   capital-increase worker hard-killed during the receipt wait (the claim and
   the recorded hash live in the row lock's transaction and roll back with it,
   so the retry finds the chain cap already raised, refuses `CAP_NOT_RAISED`
   and the DB cap has to be set by hand), the `pending` nonce the client takes
   (`integrations/base_chain/client.py`) which the row lock only serialises
   per `ShareToken`, so two workers sending for different tokens, or a mint and
   a whitelist add, in the same instant can sign the same nonce and one send
   fails with `nonce too low` (the request is marked failed and retried; safe
   now that every hash is recorded first), the row lock held across the 120 s
   receipt wait (a second executor for the same token blocks that long on a
   DB connection, and a production `idle_in_transaction_session_timeout` or
   `lock_timeout` would abort it with an `OperationalError` the task retries),
   a "Retry Deployment" while the first job is still queued or running (both
   send a create; the second reverts `CompanyAlreadyExists` and the token
   stays on the first hash, correct but noisy), an
   `eth_sendRawTransaction` whose HTTP response is lost after the node accepted
   it (the create sits in the mempool while the token returns to draft; a
   redeploy with the same symbol adopts it by identifier, but editing the
   draft's symbol first orphans the on-chain token), and the retryable
   Procrastinate tasks after crashes, duplicate delivery or uncertain RPC
   responses.
7. **Pending confirmations.** `wallets/tasks/confirmation.py` and
   `blockchain/tasks.py` mark stale transactions failed after 24 hours; there is
   no reconciliation of submitted transactions for replacement, reorgs,
   timeouts or repeated confirmation jobs, and accounting is optimistic.
8. **Company and capital validation.** `companies/models/company.py` and
   `tokens/models/capital_increase.py` do not verify director
   authority, immutable ownership, ACN/ABN validity, authorized-capital limits,
   issuance totals or concurrent capital changes.
9. **Scam detection — completed 2026-09-05.** The symbol-lookalike heuristic
   (`wallets/utils/scam_detection.py`) is gone. Asset identity for chain data
   is `(chain, contract_address)` through `AssetChainDeployment`
   (`assets/services/identity.py`): the deployment on this chain is looked
   up first and only the row carrying it is ever returned; the same address
   seen on another chain is another contract and gets its own unverified row
   (an operator adds a second chain's deployment to a verified row by hand);
   a contract the
   allowlist does not know is recorded as an unverified `Asset` with its
   deployment under a symbol no other row owns, compared case-insensitively
   (declared symbol, or symbol plus a hex prefix of the contract that grows
   until free), so neither a fake `USDC`, `usdc` nor `USDC-a0b866` can attach
   to someone else's row
   whichever contract the chain shows first; a deployment an operator
   deactivated refuses the transfer (skipped and logged); the transaction
   for a quarantined token is kept for audit but no `Holding` is opened.
   The compose `migrate` chain seeds the supported assets
   (`asset_sync --seed-only`) so no supported symbol is free on a fresh
   stack. Unverified rows are invisible to
   customers: `/api/assets/` (list, detail, snapshots), favourites, wallet
   holdings, transactions, market values, the price sync and the portfolio
   value series all filter `is_verified`, and a pending transfer naming an
   unknown or
   unverified token contract is rejected with 400 instead of debiting the
   native holding. An operator allowlists a token with the `Mark selected
   assets as verified` admin action
   (`wallets/tests/test_unknown_token_quarantine.py`).
10. **Multi-chain balance aggregation.** `wallets/services/sync.py` and the
    holdings queries scope by wallet, not by the wallet's configured chain;
    same-address balances or symbols can be merged across networks.
11. **Uploads and media.** `documents/` serves uploads through
    `MEDIA_URL` (`ledova_backend/urls.py` `static(...)`) without authenticated
    download paths, content or rendered-size limits, malware handling,
    lifecycle cleanup or denial-of-service protection.
12. **Provider logs and webhooks.** `integrations/sumsub/webhook.py`,
    `integrations/kycaid/*webhook.py` and `integrations/alchemy/webhook.py`
    verify signatures but log body lengths and identifiers and have no replay
    window; remove personal data, credentials, signed URLs and provider bodies
    from logs and errors.
13. **Dependencies and mobile hardening.** Resolve production dependency
    advisories, review native supply-chain risk, restrict cleartext networking,
    validate secure-key storage and backups, and test supported device builds.

Trading remains disabled by default (`feature_flags/middleware.py`,
`trading_enabled` flag) while these issues are open. That default is
containment, not a substitute for fixing the underlying designs.
