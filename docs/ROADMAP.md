# Roadmap

Where Ledova is going, phase by phase, and the product decisions already taken.
Security and correctness work deferred from the current release is in
[ISSUES.md](../ISSUES.md), not here.

## Direction

Ledova is infrastructure for tokenized company equity.

- An **operator** hosts a deployment, runs the Django admin, holds the deployer
  key, and receives investor payments either in AUD by bank transfer or in a
  stablecoin the platform supports or issues.
- A **company** registers, is approved, deploys a share token and issues shares
  to whitelisted investor wallets.
- An **investor** verifies identity, gets whitelisted, and holds shares in a
  verified EVM wallet.

The crypto features are rails: EVM wallets, ERC-20 transfers, a stablecoin and
an on-ramp. Bitcoin and the portfolio views are retained but secondary.

## Phase 0 — Issuance works on chain

Complete.

- Share tokens are created through `ShareTokenFactory` under the identifier
  `<acn>:<symbol>`, so one company can hold several share classes.
- Shares are minted on allotment, never at deployment: `authorizedShares` is
  the cap the company entered, and `totalSupply` grows only through executed
  issuance requests.
- Only wallets on the `WhitelistRegistry` can receive shares, and the contract
  enforces it on every transfer, not just on mint.
- Deployment, issuance and capital increases are idempotent, with receipt
  recovery and periodic sweeps for work a killed worker left in flight. Capital
  increases are serialised per token with a database row lock.
- The operator is one admin-editable configuration row exposed at
  `GET /api/operator/`.
- Company application transitions notify the owner, and the request for more
  information has a stored round trip in both clients.
- Treasury addresses can be whitelisted without a wallet.
- `make chain-test` runs the whole flow against a real Hardhat node, on SQLite
  and again on PostgreSQL, in CI.

## Phase 1 — Investor directory and primary offering

Not started. Neither exists in the code today.

- An investor directory: who the operator and issuers can see, and on what
  terms.
- A primary offering: a company publishes an offer, an investor subscribes, the
  operator records the payment (AUD bank transfer against the reference prefix,
  or a supported stablecoin to the receiving wallet) and allots the shares.
- The payment rails on the operator row exist for this and are rendered as
  instructions; nothing consumes them yet.

## Phase 2 — Eligibility and the register

Not started.

- Turn `investor_kyc_required` and `issuer_kyc_required` from stored
  configuration into actual gates. Today nothing reads them.
- A share register that is the authoritative record, reconciled against the
  chain rather than derived from it ad hoc.
- Director authority, ownership immutability, ACN and ABN validation and
  authorized-capital limits, none of which the models check today.

## Phase 3 — Settlement automation

Not started.

- Automate what an operator does by hand now: matching a received payment to a
  subscription, allotting, whitelisting, minting and issuing the confirmation.

## Phase 4 — Secondary transfers

Not started, and gated on the trading work in
[ISSUES.md](../ISSUES.md). While the `trading_enabled` flag is off,
`feature_flags/middleware.py` refuses with 403 any request, of any method, whose
path starts with one of five prefixes
(`/api/v1/trading/{orders,wallets,transfers,swaps,events}/`); the read-only
market routes (`tokens/`, `stablecoins/`) and the whitelist status route are
outside the gate by design. That default stays until the signed-intent,
concurrency and idempotency designs are fixed and independently reviewed.

## Not on the roadmap

There is no off-ramp. There is no investor directory and no primary offering
yet. Mainnet deployment configuration is deliberately absent.

## Decisions taken

- **Two deployment modes, one row.** `deployment_mode` is recorded
  configuration on the operator row
  ([docs/OPERATIONS.md](OPERATIONS.md#operator-configuration)); it does not
  change tenancy or isolation.
- **Tenant isolation stays in the ORM.** Fail-closed `visible_to_user` and
  `manageable_by_user` querysets with a pinned route matrix. PostgreSQL
  row-level security is not planned.
- **One authentication path.** The hardened `AuthViewSet` with simplejwt
  sessions and two transports. A v2 session protocol was designed and withdrawn
  unused in `0727cc2` and `33995c6`. Its ADRs,
  `backend/docs/adr/0003-authentication-session-protocol.md` and
  `0004-v2-challenge-profile.md`, were deleted later and are readable at
  `963c686` or `0ced196^`.
- **No self-service email change.** Both clients show the address read-only.
  Staff change it from the admin, which revokes every session of that user.
- **Bitcoin is watch-only plus manual signed sends** on testnet or regtest. The
  app never builds or signs a Bitcoin transaction: the user signs with their own
  tooling and pastes the raw hex, which the backend broadcasts.
- **The published compliance seed is public by design.** Its figures are the
  generic AUSTRAC-public ones. Operational thresholds and evasion-sensitive
  rules live outside this repository.
- **One shared package, consumed from source.** `@ledova/shared` has no build
  step, and both clients compile its TypeScript themselves.
- **No comments and no docstrings in source.** See the coding rules in
  [ARCHITECTURE.md](ARCHITECTURE.md).

## Open questions

- Should modifying an order re-run matching automatically? Creating one
  matches; modifying one no longer reports a candidate match.
- `NotificationPreferences` is a separate model that would fold into
  `UserPreferences` with the next settings-screen change.
