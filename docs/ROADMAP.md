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

Under way. The investor classification and the one eligibility predicate are
shipped. No investor directory and no primary offering exist in the code yet;
the only directory that does exist is the market one, `GET
/api/v1/trading/tokens/`, which lists deployed tokens.

- An investor directory: who the operator and issuers can see, and on what
  terms. Scoped by the wholesale/sophisticated decision below — the directory
  holds only investors who qualify under Corporations Act s708 and s761G, and
  the operator and issuers see only that population. What the directory is
  today, `GET /api/v1/trading/tokens/`, is a market directory of deployed
  tokens, not of investors; whether it stays unscoped is an open Phase 1
  decision (see [docs/ARCHITECTURE.md](ARCHITECTURE.md#tenancy-model)).
- An `InvestorClassification` model: the recorded basis on which an investor
  qualifies as wholesale or sophisticated, its evidence and its expiry. Shipped.
  Four categories only — `product_value` (s708(8)(a)), `accountant_certificate`
  (s708(8)(c)), `professional_investor` (s708(11) / s761G(7)(d)) and
  `associated_person` (s708(12)). The experienced-investor category
  (s708(10) / s761GA) is deliberately absent: it is the only one that turns on
  the operator holding an AFSL, and there is no evidence this deployment does.
  Adding it later is one `TextChoices` row, one migration and one form branch.
  Expiry is derived from `expires_at`, so there is no stored expired status and
  no nightly sweep. `users.services.eligibility.investor_eligibility` is the one
  predicate; the directory and the subscription flow call it, they do not
  re-derive it.
- Classification evidence is not served from `MEDIA_URL`. It streams through an
  authenticated view scoped by `visible_to_user`, so the submitting account
  reads it over the API and staff read it in the admin; both go through the
  storage backend's `open()`, so local disk and S3 behave identically and no
  presign infrastructure is needed. `CompanyDocument.get_file_url` still returns
  a plain `MEDIA_URL` path — a pre-existing exposure on ASIC extracts and
  constitutions, left standing because repointing it breaks the mobile client,
  which authenticates with a bearer token an `<img>` cannot send.
- There is no retention or auto-deletion rule for rejected and expired
  classifications. Evidence is kept until someone decides the rule. Account
  deletion behaviour is unchanged. Flagged for the owner and counsel.
- A primary offering: a company publishes an offer, an investor subscribes, the
  operator records the payment (AUD bank transfer against the reference prefix,
  or a supported stablecoin to the receiving wallet) and allots the shares.
- The payment rails on the operator row exist for this. Nothing renders them:
  `paymentInstructions` appears only as a type
  (`packages/shared/src/types/domain/operator.ts`), with no reader in
  `dashboard/src` or `mobile/src`.

## Phase 2 — Eligibility and the register

Not started, except that the Phase 1 predicate already reads the investor
switch.

- `investor_kyc_required` is now read, by
  `users.services.eligibility.investor_eligibility`: while it is on, an account
  still `pending` is refused and every holder on the account must be
  `is_id_verified`; while it is off, `pending` passes, because
  `IdentityVerificationService._process_verified_customer` is the only writer of
  `active` and it runs only on a green KYC result. `issuer_kyc_required` is
  still read by nothing.
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
market route (`tokens/`) and the whitelist status route are
outside the gate by design. That default stays until the signed-intent,
concurrency and idempotency designs are fixed and independently reviewed.

## Not on the roadmap

There is no off-ramp. There is no investor directory and no primary offering
yet: no route lists investors, and `GET /api/v1/trading/tokens/` is a directory
of deployed tokens, not of people. Retail offerings are out of scope for the
first releases (see the wholesale/sophisticated decision below). Mainnet
deployment configuration is deliberately absent.

## Decisions taken

- **Wholesale and sophisticated investors only, for the first offerings.** The
  owner has decided the first offerings are made only to investors who qualify
  under the Corporations Act 2001 (Cth) wholesale-client and sophisticated-
  investor exceptions, s708 for offers and s761G for financial-product advice,
  so no retail disclosure document is required. This is the constraint the
  Phase 1 investor directory and the Phase 2 eligibility gate are built to:
  Phase 1 records the classification, Phase 2 enforces it. Nothing in the code
  enforces it today.
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
- **No comments and no docstrings in source.** Settled, and now mechanically
  gated by `make check-comments` rather than held by review alone. See the
  coding rules in [ARCHITECTURE.md](ARCHITECTURE.md#coding-rules).

## Open questions

- Should modifying an order re-run matching automatically? Creating one
  matches; modifying one no longer reports a candidate match.
- `NotificationPreferences` is a separate model that would fold into
  `UserPreferences` with the next settings-screen change.
