# Roadmap

Where Ledova is going, phase by phase, and the product decisions already taken.
Security and correctness work deferred from the current release is tracked in
the [`deferred-hardening`](https://github.com/RonildoBraga/ledova/issues?q=is%3Aopen+label%3Adeferred-hardening) issues on GitHub, not here.

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

Under way. The investor classification, the one eligibility predicate, the
eligibility-gated directory and the `Offering` are shipped. Subscriptions,
payment confirmation and allotment are not.

- The directory is `GET /api/v1/directory/tokens/`, a new route beside the
  secondary market at `GET /api/v1/trading/tokens/`, which stays where it is.
  The two answer different questions and are scoped separately on purpose. The
  directory advertises an offer, so it lists only a share class whose issuer has
  opted in (`Company.is_open_to_investors`). The market prices shares that
  already exist, so it lists every deployed share class and does not wait on the
  issuer's listing switch — otherwise the flag defaulting to `False` would empty
  every holder's market on the day this deploys, and an existing shareholder
  would be unable to see, price or place an order on a share class only because
  its issuer had not chosen to advertise. `MARKET_ROUTES` in
  `backend/shared/tests/test_cross_tenant_routes.py` and
  `backend/tokens/tests/test_trading_tokens.py` pin that separation.
- Both listings are scoped by the wholesale/sophisticated decision below: an
  ineligible caller gets `ShareToken.objects.none()`, so the list is empty and
  every detail is a 404 byte-identical to a phantom uuid — never a 403, which
  would confirm the row exists. Two consequences worth stating plainly. An
  ineligible user's trading market overview is now empty where it previously
  listed every deployed token; that is the fix, not a regression, and both
  clients say why the list is empty rather than looking broken. And a holder who
  is not a verified wholesale investor cannot see the market for shares they
  already own, so they cannot offer them for sale here — which is the safe way
  round for s707(3) on-sale, costs nothing while the `trading_enabled` flag is
  off, and is the first thing to revisit when it is turned on.
- Only an approved offering that has opened is published to investors.
  `ShareTokenQuerySet.with_open_offering()` annotates from
  `OfferingQuerySet.open_now()`, never from `live()`, so a submitted or
  under-review offering reaches no investor and the operator's approval is what
  publishes the terms. `submit_offering` refuses a second submission on a share
  class that already has one in flight, naming it, so the ordinary
  second-tranche mistake is a 400 and not the `IntegrityError` the partial
  unique index would otherwise raise.
- **The directory is empty on day one.** `Company.is_open_to_investors` defaults
  to `False`, so no company is listed until its owner opts in from
  `/company/offering`. Nothing is broken when the directory shows nothing; the
  empty state says so in as many words. The operator can force the flag off but
  never on.
- An offering is `offerings.Offering`, in a new `offerings` app mounted twice:
  `/api/v1/offerings/` for the issuer and `/api/v1/directory/` for the investor.
  There is no `OPEN` status and no scheduler — open-now is derived from
  `approved AND opens_at <= now AND (closes_at IS NULL OR closes_at > now)`. One
  live offering per share class, refused by name in `submit_offering` and
  backstopped by a partial unique constraint; running two at once needs a
  migration and a deliberate act.
- Approve, reject and close exist only in the Django admin. The API carries
  issuer CRUD plus submit and withdraw and nothing else, so there is no staff
  API surface to mis-permission. Reaching the cap does not close an offering:
  closing is a deliberate operator act, and nothing closes an offering on its
  own. **Planned, not built:** a "cap reached, not closed" row in the operator
  console. There is no operator console yet; the row arrives with it.
- The economics of an offering are frozen once it leaves draft. The admin change
  form keeps the share class, the exemption, the price, the bounds, the payment
  rails and the window editable only while the row is a draft, because the
  checks that guard them live in `submit_offering` and re-running them from an
  admin form's `clean` would be a second copy of the same rules, free to drift.
  Approving re-runs the headroom check itself, so a `ShareIssuance` that
  completes between the submission and the operator's approval refuses the
  approval by name rather than publishing a cap the share class can no longer
  cover. `submit_offering` takes a `select_for_update` on the share-class row
  before it reads the live offerings, the way `_execute_capital_increase` does,
  so two simultaneous submissions on one share class end in one submission and
  one 400 that names the offering in flight, never the `IntegrityError` the
  partial unique index would otherwise turn into a 503.
- The exemption choices deliberately exclude the experienced-investor category
  (s708(10) / s761GA), for the same reason `InvestorCategory` does.
- An `InvestorClassification` model: the recorded basis on which an investor
  qualifies as wholesale or sophisticated, its evidence and its expiry. Shipped.
  Four categories only — `product_value` (s708(8)(a)), `accountant_certificate`
  (s708(8)(c)), `professional_investor` (s708(11) / s761G(7)(d)) and
  `associated_person` (s708(12)). The experienced-investor category
  (s708(10) / s761GA) is deliberately absent: it is the only one that turns on
  the operator holding an AFSL, and there is no evidence this deployment does.
  Adding it later is one `TextChoices` row, one migration and one form branch.
  Expiry is derived from `expires_at`, so there is no stored expired status and
  no nightly sweep. `users.services.eligibility` is the one predicate, with two
  subjects. `investor_eligibility(user)` answers a question about a person and
  is what the directory asks: may this user see offerings at all. Everything
  that binds a specific account — a subscription, a whitelist entry — asks
  `account_eligibility(account)` / `require_subscription_eligibility(account,
  company, amount)` instead, because a user with two investor accounts earns a
  `True` on one of them and must not spend it on the other. The predicate never
  infers the account from the user for those callers; the caller names it.
- An account may hold more than one live claim, so eligibility asks whether
  *any* live claim supports the offer, not what the newest one says. A live
  `professional_investor` claim qualifies a AUD 1,000 subscription even when a
  `product_value` claim was recorded more recently, and the AUD 500,000 floor
  still refuses an account whose only live claim is `product_value`. Where no
  amount is in play the newest live claim is the one reported.
- **An `associated_person` claim reaches less of the directory than the other
  three categories, and that is deliberate.** Section 708(12) associates a
  person with one named issuer, so the claim names a `Company` and carries no
  weight anywhere else. A caller whose only live claim is an association with
  company A sees exactly company A's share classes in the directory, gets a 200
  on their detail pages, and gets the same 404 as a phantom uuid on every other
  issuer. The other three categories are unscoped and reach every listed issuer.
  A caller holding both kinds of live claim reaches everything, on the strength
  of the unscoped one. An association also opens the operator's payment rails at
  `GET /api/operator/`, because an associate can subscribe to the issuer they
  are associated with and has to be told where the money goes. It does not widen
  the secondary market at `GET /api/v1/trading/tokens/`, which stays on the
  unscoped predicate: s708(12) is about an issuer's offer, not about a market in
  shares that already exist.
- `GET /api/operator/` withholds `payment_instructions` — the operator's bank
  account name, BSB, account number, reference prefix and receiving wallet —
  from a caller who is neither staff nor an eligible investor of some company.
  It asks the same B3 predicate the directory is scoped by, not a second one.
  The rest of the operator payload is identical for every caller, and the
  withheld key is present and `null` rather than absent, so the payload shape
  does not change with the caller.
- Classification evidence is not served from `MEDIA_URL`, and the bytes do not
  live under `MEDIA_ROOT` at all. On the local backend they are written to
  `PRIVATE_MEDIA_ROOT` (`backend/private-media`) through
  `shared.storage.PrivateMediaStorage`, which has no `base_url`, so
  `evidence_file.url` raises rather than handing anyone a path; on S3 and GCS
  the same private, signed bucket configuration as every other upload. Hiding
  the link was not enough: `django.conf.urls.static` serves the whole of
  `MEDIA_ROOT` to anonymous callers whenever `DEBUG` is true, which is the
  configuration `docker-compose.yml` and `backend/.env.example` ship, so a
  net-asset statement under `MEDIA_ROOT` is one copied URL away from the public.
  Reading it goes through the storage backend's `open()` in both places — the
  submitting account over the API scoped by `visible_to_user`, staff through the
  admin — so local disk and S3 behave identically and no presign is needed. The
  admin change form shows only that streaming link; the raw `FileField` is not
  in `fieldsets`, and putting it in `readonly_fields` would not do, because
  Django renders a readonly `FileField` as an `<a href>` on `value.url`.
- `CompanyDocument.get_file_url` still returns a plain `MEDIA_URL` path, so on a
  deployment running `DEBUG=true` every uploaded ASIC extract and constitution
  is readable with no session. Lower sensitivity than net-asset evidence and
  left standing because repointing it breaks the mobile client, which
  authenticates with a bearer token an `<img>` cannot send — but it is an
  exposure, not merely a rough edge, and closing it means giving the clients a
  streaming endpoint the way classification evidence has one.
- There is no retention or auto-deletion rule for rejected and expired
  classifications. Evidence is kept until someone decides the rule. Account
  deletion behaviour is unchanged. Flagged for the owner and counsel.
- A primary offering: a company publishes an offer, an investor subscribes, the
  operator records the payment (AUD bank transfer against the reference prefix,
  or a supported stablecoin to the receiving wallet) and allots the shares.
- The payment rails on the operator row exist for this. The directory detail
  page renders `paymentInstructions` from `GET /api/operator/` rather than
  duplicating bank details onto the offering, so there is one copy of the
  operator's BSB and receiving wallet and one place to change it. It asks for
  them only once the share class itself has resolved, so a caller whose detail
  request 404s never requests the rails at all.
- Allotted shares now reach the portfolio. Deploying a share token writes a
  verified `assets.Asset` (`tokenized_security`, `decimals` 0) and an
  `AssetChainDeployment` at the address the factory attests, and completing an
  issuance writes the recipient's `Holding` from `balanceOf`. Share tokens
  deployed before this existed are bridged by
  `manage.py bridge_share_assets`, which is idempotent and never runs on its
  own.

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
- A share register that is the authoritative record, reconciled against the
  chain rather than derived from it ad hoc.
- Director authority, ownership immutability, ACN and ABN validation and
  authorized-capital limits, none of which the models check today.

## Phase 3 — Settlement automation

Not started.

- Automate what an operator does by hand now: matching a received payment to a
  subscription, allotting, whitelisting, minting and issuing the confirmation.

## Phase 4 — Secondary transfers

Not started, and gated on the trading work in the
[`deferred-hardening`](https://github.com/RonildoBraga/ledova/issues?q=is%3Aopen+label%3Adeferred-hardening) issues. While the `trading_enabled` flag is off,
`feature_flags/middleware.py` refuses with 403 any request, of any method, whose
path starts with one of five prefixes
(`/api/v1/trading/{orders,wallets,transfers,swaps,events}/`); the read-only
market route (`tokens/`) and the whitelist status route are outside that gate by
design, and the market route is gated on investor eligibility instead. That
default stays until the signed-intent, concurrency and idempotency designs are
fixed and independently reviewed.

## Not on the roadmap

There is no off-ramp. No route lists investors: `GET /api/v1/directory/tokens/`
is a directory of deployed share classes open to investors, not of people. There
is no subscription, no payment confirmation and no allotment from an offering
yet. Retail offerings are out of scope for the first releases (see the
wholesale/sophisticated decision below). Mainnet deployment configuration is
deliberately absent.

## Decisions taken

- **Wholesale and sophisticated investors only, for the first offerings.** The
  owner has decided the first offerings are made only to investors who qualify
  under the Corporations Act 2001 (Cth) wholesale-client and sophisticated-
  investor exceptions, s708 for offers and s761G for financial-product advice,
  so no retail disclosure document is required. This is the constraint the
  Phase 1 investor directory and the Phase 2 eligibility gate are built to:
  Phase 1 records the classification, Phase 2 enforces it. Nothing in the code
  enforces it today.
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
  refuses a `tokenized_security`, and so does `broadcast-transfer` whenever the
  caller names the token contract. A broadcast that omits the contract carries
  an opaque signed transaction the backend cannot inspect, so the guard there is
  advisory rather than absolute. What actually holds the line is on chain:
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
