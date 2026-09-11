# Roadmap

Where Ledova is going, phase by phase, and the product decisions already taken.

**This document does not describe how shipped things work.** A completed phase
says what shipped and links to [ARCHITECTURE.md](ARCHITECTURE.md) or
[OPERATIONS.md](OPERATIONS.md); a decision is recorded here only where the
choice and its reason are not readable from the code. Re-describing shipped
behaviour here is what let four claims outlive the code that changed them.

Security and correctness work deferred from the current release is tracked in
the [`deferred-hardening`](https://github.com/RonildoBraga/ledova/issues?q=is%3Aopen+label%3Adeferred-hardening) issues on GitHub, not here.

## Direction

Ledova is a platform for creating and operating digital private equity markets.
[README.md](../README.md) carries the product definition in the owner's words —
the problem, the solution and the twelve core features — and this document defers
to it wherever the two differ.

- An **operator** hosts a deployment, runs the Django admin, holds the deployer
  key, and receives investor payments either in AUD by bank transfer or in a
  stablecoin the platform supports or issues.
- A **company** registers, is approved, deploys a share token and issues shares
  to whitelisted investor wallets.
- An **investor** verifies identity, gets whitelisted, and holds shares in a
  verified EVM wallet.

The crypto features are rails: EVM wallets, ERC-20 transfers, a stablecoin and
an on-ramp.

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

Complete. What shipped:

- **The investor classification and the one eligibility predicate.**
  `InvestorClassification` records the basis on which an investor qualifies,
  its evidence and its expiry; `users.services.eligibility` is the single
  predicate over it, with two subjects — `investor_eligibility(user)` for
  "may this person see offerings at all", `account_eligibility(account)` and
  `require_subscription_eligibility(...)` for anything binding one account.
- **The eligibility-gated directory** at `GET /api/v1/directory/tokens/`,
  beside the secondary market at `GET /api/v1/trading/tokens/`. The two answer
  different questions and are scoped separately on purpose.
- **The offering**, `offerings.Offering`: issuer CRUD, submit and withdraw on
  the API; approve, reject and close in the admin only, so there is no staff
  API surface to mis-permission. No `OPEN` status and no scheduler — open-now
  is derived.
- **The subscription and its money**: payment instruction, confirmation on
  either rail, partial payment, refund, scale-back and allotment, with the
  guards that stop a double mint and stop money going back while shares are
  out.
- **The register of members**, current and former, and its s169-shaped CSV.
- **The operator console** at `/admin/operators/operator/`: a configuration
  health strip, thirteen worklist counts, and the deployment mode with the
  register keeper for each active company.
- **Private storage for every upload**, and a retention horizon on
  classification evidence enforced by the four serving paths and a nightly
  sweep.

How each works is in [ARCHITECTURE.md](ARCHITECTURE.md) — the offering,
subscription and issuance data flows, the register, the tenancy model and
uploaded files. How an operator runs them is in
[OPERATIONS.md](OPERATIONS.md) — the operator row and console, seeding,
retention settings and background jobs. The choices behind them are under
[Decisions taken](#decisions-taken).

## Phase 2 — Eligibility and the register

Part shipped. The eligibility predicate, its enforcing readers and the
former-member fold landed with Phase 1. Company models already have ACN and ABN
validation hooks. The authoritative current-members register and the remaining
company checks are unfinished.

- `investor_kyc_required` is now read, by
  `users.services.eligibility.investor_eligibility`: while it is on, an account
  still `pending` is refused and every holder on the account must be
  `is_id_verified`; while it is off, `pending` passes, because
  `IdentityVerificationService._process_verified_customer` is the only writer of
  `active` and it runs only on a green KYC result. `issuer_kyc_required` is
  still read by nothing.
- The eligibility predicate now has enforcing readers.
  `DirectoryTokenViewSet` narrows its queryset to
  `eligible_investor_companies(user)`, which is `investor_eligibility(user)`
  first and, only when that refuses, the companies the caller's live
  `associated_person` claims name and that `investor_eligibility(user,
  company=...)` then accepts one by one. An unreachable company is filtered out
  of the queryset rather than refused, so the answer is 404, never 403.
  `TradingTokenViewSet` still asks the unscoped `investor_eligibility(user)` and
  narrows to `ShareToken.objects.none()` on a refusal. Both call the non-raising
  entry point rather than `require_investor_eligibility`, because the raising
  one produces the 403 these listings must never emit;
  `require_investor_eligibility` therefore still has no production caller and
  the subscription flow is where it belongs. `OperatorSerializer` is the third
  reader, through `eligible_for_any_company(user)`, and the whitelist admin's
  read-only column and add-form warning remain the fourth.
- A current-members register that is the authoritative record rather than
  derived. The trigger condition is in
  [ARCHITECTURE.md](ARCHITECTURE.md#the-register-of-members): the moment a share
  can move by anything other than allotment, a transferee who never received one
  is invisible to it. The `Transfer` fold Phase 1 built for former members is the
  half of this that exists; current holders still come from allotments
  reconciled against `balanceOf`. A durable queryable record of every register
  export waits on the same work — today it is one application log line.
- Company model validation includes ACN and ABN field validators and their
  consistency check in `Company.clean()`. These hooks do not make every ORM
  write run validation. Director authority, ownership immutability and
  authorized-capital limits remain separate completion checks.

## Phase 3 — Settlement automation

Not started.

- Automate what an operator does by hand now: matching a received payment to a
  subscription, allotting, whitelisting, minting and issuing the confirmation.
  Phase 1 does each of those from the admin with one click; Phase 3 is where a
  bank feed and a chain watcher propose the match instead of the operator
  reading a statement, and where `SubscriptionPayment` earns its place if
  multi-tranche reconciliation is still wanted then.
- **The provider is undecided, and the requirement is not.** The owner has
  chosen to pick a bank feed or payment service when Phase 3 is scheduled
  rather than now, so nothing here names one. What any provider must give is
  fixed: **incoming AUD transfers carrying their reference text**, delivered
  through **a webhook or a poll**. The reference format is not negotiable with
  a provider — `normalize_reference`, the Crockford alphabet and the
  operator's prefix followed by an eight-character code
  (`REFERENCE_CODE_LENGTH`) are what the platform issues, inside the
  18-character field a reference must fit (`MAX_REFERENCE_LENGTH`), and a
  provider must carry them unchanged. The two
  shapes the desk weighed are a read-only open-banking feed on the operator's
  own account and a payments provider issuing a PayID or virtual account per
  subscription; the choice between them is the scheduled question. The
  stablecoin rail's chain watcher is the other half of Phase 3 and needs no
  provider at all.
  ([B7c](https://github.com/RonildoBraga/ledova/issues/115#issuecomment-5574962513))

## Phase 4 — Secondary transfers

**Mobile's investor half lands in this phase.** The owner has decided that the
investor directory and the subscription flow reach mobile in Phase 4 — offering
detail, subscription on both rails, and the payment-instruction and allotment
views — over the hooks Phase 2 is producing. Features 4 and 5 are
dashboard-only for investors until then, which is why nothing is built on
mobile before this phase. It is a constraint on Phase 2 rather than a note
about Phase 4: **a shared hook moved now is designed for both clients**,
because the second client is scheduled rather than hypothetical. B7b's other
half — the README's mobile mention gaining "Phase 4" beside it — belongs to the
next docs pass and is not in this change. Issuers are dashboard-only this
phase, which is B2 rather than this decision; B7b is silent on the issuer half.
([B7b](https://github.com/RonildoBraga/ledova/issues/115#issuecomment-5574947880),
[B2](https://github.com/RonildoBraga/ledova/issues/115#issuecomment-5574848881))

Not started, and gated on the trading work in the
[`deferred-hardening`](https://github.com/RonildoBraga/ledova/issues?q=is%3Aopen+label%3Adeferred-hardening) issues. The `trading_enabled` flag stays off until the
signed-intent, concurrency and idempotency designs are fixed and independently
reviewed; what the flag refuses while it is off is in
[README.md](../README.md#safety-defaults).

## Not on the roadmap

There is no off-ramp. No route lists investors: `GET /api/v1/directory/tokens/`
is a directory of deployed share classes open to investors, not of people. The
register of members is per share class, is read only by the issuer that owns it
and by the operator, and is not a route anyone else can reach. Retail offerings
are out of scope for the first releases (see the wholesale/sophisticated
decision below). Mainnet deployment configuration is deliberately absent.

## Decisions taken

- **Wholesale and sophisticated investors only, for the first offerings.** The
  owner has decided the first offerings are made only to investors who qualify
  under the Corporations Act 2001 (Cth) wholesale-client and sophisticated-
  investor exceptions, s708 for offers and s761G for financial-product advice,
  so no retail disclosure document is required. `InvestorClassification` records
  the basis and the directory, the market and the subscription flow are all
  scoped by it. An ineligible caller gets an empty list and a 404 on every
  detail byte-identical to a phantom uuid — never a 403, which would confirm the
  row exists.
- **A holder who is not a verified wholesale investor cannot see the market for
  shares they already own.** That follows from scoping the market by the same
  predicate, and it is the safe way round for s707(3) on-sale: they cannot offer
  those shares for sale here. It costs nothing while `trading_enabled` is off,
  and it is the first thing to revisit when it is turned on.
- **Four classification categories, and deliberately not a fifth.**
  `product_value` (s708(8)(a)), `accountant_certificate` (s708(8)(c)),
  `professional_investor` (s708(11) / s761G(7)(d)) and `associated_person`
  (s708(12)). The experienced-investor category (s708(10) / s761GA) is absent
  because it is the only one that turns on the operator holding an AFSL, and
  there is no evidence this deployment does. Adding it later is one
  `TextChoices` row, one migration and one form branch. The offering exemption
  choices exclude it for the same reason.
- **An `associated_person` claim is scoped to the issuer it names.** Section
  708(12) associates a person with one issuer, so such a claim reaches that
  company's share classes in the directory and no others, and does not widen the
  secondary market at all — that is about a market in shares that already exist,
  not about one issuer's offer.
- **Payment confirmation is columns on the subscription, not a second model.**
  The first offerings are tens of subscriptions and the admin `LogEntry` already
  records who changed what. The trade-off is named rather than hidden:
  multi-tranche reconciliation against a bank statement is not supported, and a
  second tranche is the operator updating the total with a note. Adding a
  `SubscriptionPayment` table later is purely additive.
- **Amount paid on the register is blank where it is not exactly known, never
  zero.** A holding that predates the platform has no subscription behind it,
  and a zero against it would be a false record rather than a missing one. The
  three conditions that blank it are in
  [ARCHITECTURE.md](ARCHITECTURE.md#the-register-of-members).
- **Share classes stay out of the general asset list.** `GET /api/assets/`
  excludes `tokenized_security`, so one company's share class is not visible to
  every authenticated user through the market card, the asset-prices screen or
  the favourites picker. Discovery belongs to the eligibility-gated investor
  directory. A holder still sees their own shares through
  `GET /api/wallets/{uuid}/holdings/`.
- **A share Asset carries no price.** `current_price` stays null for a
  tokenized security: a nominal issue price on an unlisted illiquid security
  would flow into total market value and the performance percentage, which is a
  valuation claim the platform cannot make. The consequence is cosmetic and
  pinned by tests — a shares-only portfolio draws a flat zero holdings chart
  instead of the empty state, and its allocation doughnut is empty while the
  quantity column shows the real share count.
- **Shares move by allotment, not by wallet transfer.** `prepare-transfer`
  refuses a `tokenized_security`, and so does `broadcast-transfer`, which no
  longer depends on the caller naming the token contract: an EVM broadcast is
  decoded before anything reaches the chain, and the decode refuses a share
  token target, a foreign chain id, contract creation, an ERC-20 `transfer`
  that also carries native value, and any payload that is neither a plain
  native send nor an ERC-20 `transfer`. The recipient, amount and asset of the
  recorded `Transaction` row are written from the decoded transaction, not from
  the request body; `from_address` is still the wallet's own address, because
  the decode does not yet require the recovered signer to be that address.
  What also holds the line is on chain:
  `ShareToken._update` reverts unless the recipient is in the whitelist
  registry, so a share can never leave the whitelisted set and the Phase 1
  register — a read-model over `ShareIssuance` reconciled against on-chain
  balances — stays reconstructible. The register is only *complete* while
  allotment is the sole way shares move, which is why the trading write routes
  remain flag-gated. Relaxing either is the trigger for a Phase 2 log indexer.
- **Two deployment modes, one row.** `deployment_mode` is recorded
  configuration on the operator row
  ([docs/OPERATIONS.md](OPERATIONS.md#operator-configuration)); it does not
  change tenancy or isolation.
- **Tenant isolation stays in the ORM, with PostgreSQL row-level security being
  added underneath it.** Fail-closed `visible_to_user` and
  `manageable_by_user` querysets with a pinned route matrix remain the live
  mechanism; RLS is a second floor under them, added in stages. See
  "Tenancy model" in `docs/ARCHITECTURE.md`.
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
  tooling and pastes the raw hex, which the backend broadcasts. There is no
  Bitcoin transaction decoder, so on that chain alone `broadcast-transfer` still
  records the recipient and amount the caller declares.
- **The published compliance seed is public by design.** Its figures are the
  generic AUSTRAC-public ones. Operational thresholds and evasion-sensitive
  rules live outside this repository.
- **One shared package, consumed from source.** `@ledova/shared` has no build
  step, and both clients compile its TypeScript themselves.
- **Classification evidence is kept for a fixed period, then purged.** Shipped
  as a derived read-horizon plus a nightly sweep, with the period as a deploy-time
  setting. The shape is settled; the period is seven years on the reading in
  [LEGAL.md](LEGAL.md), taken without advice.
- **No comments and no docstrings in source.** Settled, and now mechanically
  gated by `make check-comments` rather than held by review alone. See the
  coding rules in [GATES.md](GATES.md#the-rules).
- **One portfolio line per asset, summed across chains.** The owner has decided
  the portfolio shows one line and one ring slice per asset, summing the
  `Holding` rows across every chain it is held on, with the per-chain split
  visible when the line is expanded. Send and receive go on choosing a chain,
  because a transfer happens on one. The asset model does not change. This is
  the display rule the rest of #10 is built to, and it composes with the
  value-source label B5 settled, which
  [#346](https://github.com/RonildoBraga/ledova/issues/346) still has to carry:
  a summed line says what it is a sum of, and an unpriced holding contributes
  zero, and says so rather than doing it silently.
  ([B7d](https://github.com/RonildoBraga/ledova/issues/115#issuecomment-5574975348))
- **The shared types are generated, once there is something to generate from.**
  The owner has decided `packages/shared/src/types` is generated from the
  OpenAPI schema — not now, but when every client-facing endpoint is declared
  and [#209](https://github.com/RonildoBraga/ledova/pull/209)'s drift gate has
  run clean across a release. Until then the hand-written types stay, and that
  gate refuses drift between them and the schema once it merges. The order
  matters and is the whole decision: generating early would produce
  types for the endpoints that happen to be declared and silence the gate for
  the ones that are not. The hand-written files retire in the same PR that
  generates their replacements, and the drift gate becomes the generation step
  rather than being deleted.
  ([B7e](https://github.com/RonildoBraga/ledova/issues/115#issuecomment-5575002254))

## Open questions

- **Four legal positions are taken without advice**, in [LEGAL.md](LEGAL.md):
  s169(3) retention of former members, who carries the s168 obligation to keep
  the register, the period behind
  `CLASSIFICATION_EVIDENCE_RETENTION_DAYS`, and the exception relied on to run
  without a licence. None is engaged while the platform is testnet-only with
  synthetic data, and that document carries the trigger for each. The fourth is
  the one that is not settled by reading, and the position on it is to not reach
  its trigger.
- Should modifying an order re-run matching automatically? Creating one
  matches; modifying one no longer reports a candidate match.
- `NotificationPreferences` is a separate model that would fold into
  `UserPreferences` with the next settings-screen change.
