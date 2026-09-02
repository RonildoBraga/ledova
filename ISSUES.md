# Deferred high-risk work

This document records known high-risk work intentionally deferred from the
experimental local/testnet release. Open areas require implementation, tests,
and independent review before any public multi-user or real-value use.

1. **Tenant isolation and authorization — completed 2026-09-02.** Customer
   queries and mutations are self-scoped through the `visible_to_user` /
   `manageable_by_user` querysets, every detail route and action is covered by
   the cross-tenant route matrix, and global operator routes require explicit
   admin access. PostgreSQL RLS is not planned.
2. **Authentication, sessions, and CSRF.** Implement the explicit browser and
   native transports, stateful sessions, refresh rotation, email challenges,
   and lifecycle gates accepted in
   [ADR 0003](backend/docs/adr/0003-authentication-session-protocol.md).
3. **SSE query JWTs.** Replace event-stream authentication that places bearer
   tokens in URLs, where proxies, browser history, and logs can retain them.
4. **Signed-intent binding and replay.** Bind every signature to one reviewed
   action, account, chain, contract, amount, recipient, nonce, and short expiry;
   consume each challenge exactly once.
5. **Trading concurrency and idempotency.** Add database locking, state-machine
   invariants, replay protection, and idempotency keys around order and swap
   creation, modification, cancellation, matching, and settlement.
6. **On-chain and background-job idempotency.** Make deployment, minting,
   issuance, capital-increase, whitelist, and retryable worker tasks safe after
   crashes, duplicate delivery, and uncertain RPC responses.
7. **Pending confirmations.** Persist and reconcile submitted transactions
   without optimistic final accounting; handle replacement, reorgs, failures,
   timeouts, and repeated confirmation jobs.
8. **Company and capital validation.** Verify company/director authority,
   immutable ownership relationships, ACN/ABN handling, authorized-capital
   limits, issuance totals, and concurrent capital changes.
9. **Scam detection.** Replace symbol- and metadata-based token trust with
   chain-and-contract identity, explicit verification, and quarantine for
   unknown assets.
10. **Multi-chain balance aggregation.** Scope native and token balances to the
    wallet's configured chain and prevent same-address balances or symbols from
    being merged across networks.
11. **Uploads and media.** Enforce authenticated download paths, content and
    rendered-size limits, owner-only storage, malware handling, lifecycle
    cleanup, and denial-of-service protections.
12. **Provider logs and webhooks.** Remove personal data, credentials, signed
    URLs, provider bodies, and identifiers from logs and errors; fail closed on
    webhook authentication and validate replay windows.
13. **Dependencies and mobile hardening.** Resolve production dependency
    advisories, review native supply-chain risk, restrict cleartext networking,
    validate secure-key storage and backups, and test supported device builds.

Trading remains disabled by default while these issues are open. That default
is containment, not a substitute for fixing the underlying designs.
