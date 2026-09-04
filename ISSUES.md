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
6. **On-chain and background-job idempotency.** Deployment
   (`tokens/services/share_token_service.py`, `tokens/tasks/`), minting
   (`tokens/services/mint_service.py`), issuance, capital increase, whitelist
   (`whitelist/services/whitelist.py`) and the retryable Procrastinate tasks
   are not safe after crashes, duplicate delivery or uncertain RPC responses.
7. **Pending confirmations.** `wallets/tasks/confirmation.py` and
   `blockchain/tasks.py` mark stale transactions failed after 24 hours; there is
   no reconciliation of submitted transactions for replacement, reorgs,
   timeouts or repeated confirmation jobs, and accounting is optimistic.
8. **Company and capital validation.** `companies/models/company.py` and
   `tokens/models/capital_increase.py` do not verify director
   authority, immutable ownership, ACN/ABN validity, authorized-capital limits,
   issuance totals or concurrent capital changes.
9. **Scam detection.** `wallets/utils/scam_detection.py` trusts symbols and
   metadata; replace it with chain-and-contract identity, explicit
   verification (`Asset.is_verified`) and quarantine for unknown assets.
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
