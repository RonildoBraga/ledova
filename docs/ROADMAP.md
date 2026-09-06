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

Complete. The investor classification, the one eligibility predicate, the
eligibility-gated directory, the `Offering`, the subscription, payment
confirmation and allotment flow, the register of members and the operator
console are all shipped.

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
- Company documents are closed the same way classification evidence was, and the
  bytes have left `MEDIA_ROOT`. `CompanyDocument.file` binds
  `shared.storage.private_storage`, so `file.url` raises rather than handing out
  a path, and reading goes through
  `GET /api/v1/companies/<company>/documents/<uuid>/file/`, scoped by
  `visible_to_user` and identical on local disk and S3.
  Until this shipped, `get_file_url` returned a plain `MEDIA_URL` path, so on a
  deployment running `DEBUG=true` — the configuration `docker-compose.yml` and
  `backend/.env.example` ship — every uploaded ASIC extract and constitution was
  readable with no session at all. That was an exposure, not a rough edge, and a
  test now pins it: `test_an_anonymous_caller_cannot_fetch_the_document_from_media_under_debug`
  reloads the urlconf with `DEBUG=True` and asserts the raw path 404s.
- Staff read a company document through the admin, never through the API. The
  API stays owner-only, because `CompanyQuerySet.visible_to_user` is
  `filter(owner=user)` with no staff exception and
  `test_querysets_fail_closed_and_follow_company_ownership_for_privileged_users`
  pins that a superuser sees only their own. The consequence worth stating: the
  staff-only `POST /api/v1/companies/<uuid>/status/` response nests document
  payloads whose `fileUrl` a staff caller cannot fetch. That is deliberate —
  widening the queryset to make it work would undo the tenant scoping.
- The existing `file` migration changes storage, so it moves bytes as well as
  schema. `0006_company_document_private_storage` relocates every stored file
  from `MEDIA_ROOT` to `PRIVATE_MEDIA_ROOT`, guarded on
  `STORAGE_BACKEND == "local"` because `PRIVATE_MEDIA_ROOT` is not defined on
  S3 or GCS and the move is a no-op there anyway. An `AlterField` alone would
  have left the old uploads sitting in the served directory — the exposure
  surviving the fix for exactly the rows it was meant to protect.
- Mobile could not keep opening documents with `Linking.openURL`: it
  authenticates with a bearer token, and the OS browser sends neither that nor a
  cookie. It now fetches through `apiClient`, writes to the cache directory and
  hands the file to `expo-sharing`. The dashboard needed no such change — its
  `<a target="_blank">` is a top-level navigation that carries the `SameSite=Lax`
  session cookie. Mobile has no test runner, so that half ships unverified.
- Rejected, revoked and expired classifications keep their evidence for a fixed
  period and are then purged automatically, leaving the classification record and
  its outcome behind. Shipped. One horizon, two enforcers: the four serving paths
  — the API evidence route, the admin evidence view, the admin link and the
  serializer's `evidenceUrl` — all refuse past it, so a claim stops being
  readable the moment it crosses rather than up to a day later when the sweep
  runs, and it stays refused if the worker is dead; `purge_classification_evidence`
  then deletes the bytes nightly, because deletion is a side effect and cannot be
  derived the way `expires_at` is. No status column records the purge — a cleared
  `evidence_file` is the record, matching the choice `expires_at` makes in
  storing no expired status. The clock is `reviewed_at` for a rejected or revoked
  claim and `expires_at` for one that expired, so a revoked claim runs from its
  review and not from the stale expiry `verify` left on it; a claim with no clock
  stamped is never swept. `evidence_file_size` and `evidence_mime_type` survive,
  being content-free metadata rather than the document.
- **The retention period is configuration, and its value is still open.**
  `CLASSIFICATION_EVIDENCE_RETENTION_DAYS` is a deploy-time setting rather than an
  admin-editable field, because purging is irreversible and shortening a statutory
  window should take a deploy and a review rather than one form submit. The
  shipped default of 2557 days is a placeholder, not advice; Australian
  financial-record and AML/CTF customer-identification obligations are the
  constraints to confirm it against. `0` retains indefinitely and purges nothing.
- **Account deletion does not purge evidence early, deliberately.**
  `delete_account` is a tombstone that never touches `InvestorClassification`, so
  evidence already survived deletion; that is now a decision rather than an
  oversight. A fixed retention period exists precisely to outlive the subject's
  wishes, which is usually why the obligation to keep the record exists at all.
- A primary offering: a company publishes an offer, an investor subscribes, the
  operator records the payment (AUD bank transfer against the reference prefix,
  or a supported stablecoin to the receiving wallet) and allots the shares.
  Shipped, as `offerings.Subscription` plus `POST /api/v1/subscriptions/`.
- **Payment confirmation is columns on the subscription row, not a second
  model.** The first offerings are tens of subscriptions, and Django's admin
  `LogEntry` already records who changed what and when. Partial payment is the
  operator confirming the amount that actually arrived and, when accepting it as
  final, scaling `allotted_quantity` to `floor(received / price)` with the
  sub-share residual recorded as a refund owed. The trade-off is named rather
  than hidden: multi-tranche reconciliation against a bank statement is not
  supported, and a second tranche is the operator updating the total with a
  note. Adding a `SubscriptionPayment` table later is purely additive.
- **Reject and withdraw are refused once any money is recorded.** The operator
  must record a refund first; only then does the row accept a rejection or a
  withdrawal. Money that arrived cannot be waved away by a status change, and
  the API's withdraw route refuses it the same way the admin does.
- **Money out never leaves shares out.** A subscription stays `paid` from the
  Allot click until the deferred task runs, which is minutes with the retry
  strategy, and the admin offers Record refund throughout that window.
  `record_refund` therefore claims the linked issuance request first: a
  compare-and-set from `EXECUTABLE_STATUSES` to `rejected` inside the refund's
  transaction, so either the refund wins and `execute_request` refuses the mint,
  or the worker's `mark_executing` won and the refund is refused by name. Once
  the request is `executing` or `executed` — including the reconciler window
  where the shares are minted but the row still reads `paid` — a refund, a
  rejection, a withdrawal and a restated payment are all refused. The request
  status alone is not enough: `EXECUTABLE_STATUSES` includes `failed`, and a
  mint that was broadcast and then lost its receipt to an RPC timeout leaves the
  request `failed` with the shares already out, so a status-only guard let the
  money go back while they stood. What settles it is the discriminator the
  issuance model already carries — `mark_reverted` clears `tx_hash` because a
  reverted mint is safe to refund, `mark_failed` keeps it because a broadcast
  mint of unknown fate is not — so every money move is refused while the linked
  `ShareIssuance` carries a hash, and only the executing sweep releases it, by
  completing the mint or by clearing the hash on a revert.
- **A lost receipt is swept, not left for someone to notice.**
  `check_executing_issuance_requests` takes `executing` requests and also
  `failed` ones whose issuance still carries a `tx_hash`. The allotment task
  retries four times on a receipt timeout and then gives up, and before this the
  row stayed `failed` with a mint out: the reconciler only flips `executed` rows
  and the sweep only looked at `executing` ones. Both ends now close on their
  own — the mint completes and the subscription mirrors to `allotted`, or the
  revert clears the hash and the refund reopens.
- **Two sequential batches cannot jointly outrun the authorized supply.**
  `totalSupply()` counts minted shares, not promised ones, so a batch judged
  only against `authorized - issued` fits while the requests approved by the
  previous batch are still unexecuted. The chain half of the headroom therefore
  subtracts every request for the token that can still mint — `approved`,
  `executing`, and `failed` while its issuance carries a hash. Nothing was
  over-minted before the fix, because `execute_request` and the contract both
  refuse, but `mark_refused` leaves the request `approved`, so the second
  subscription sat `paid` with the money in, no shares, and a task that failed
  on every retry.
- **Eligibility is re-checked at acceptance, not only at submission.** A
  certificate can lapse in between and the law cares about status at
  acceptance, so `accept` runs `require_subscription_eligibility(account,
  company, amount)` again. Both calls name the subscription's own account: a
  user with two investor accounts earns a qualification on one and must not
  spend it on the other.
- **Nothing may mint twice.** A subscription's allotment rests on three
  mechanisms that already existed and were not weakened: the `OneToOne` from
  `Subscription.issuance_request`, claimed under `select_for_update` so two
  simultaneous clicks produce one request; the unique
  `ShareIssuance.idempotency_key`, derived from that request's uuid; and the
  compare-and-set in `ReviewableRequest.mark_executing`. Allotment reimplements
  none of the mint: it calls `create_issuance_request`, `approve`, links the
  request and defers a task onto the untouched `execute_request`.
  `backend/offerings/tests/test_chain_allotment.py` proves it on a live Hardhat
  node, sequentially and with two workers racing.
- **One on-chain transfer cannot fund two subscriptions.** A partial unique
  constraint on `Lower(Subscription.payment_tx_hash)` where it is non-empty says
  so at the database level, and the service refuses the second confirmation by
  name before it gets there. The fold is not cosmetic: an Ethereum transaction
  hash is case-insensitive hex with no checksum encoding, so an explorer and a
  CSV export of the same transfer differ in case, and a byte-exact index would
  let that one transfer fund two subscriptions. `confirm_payment` normalises the
  hash to lower case and refuses anything that is not `0x` plus 64 hexadecimal
  characters. The payment reference is unique the same way.
- **A payment reference is normalised on generation as well as on lookup**, so a
  mangled bank narrative still matches: the prefix and an eight-character
  Crockford base32 code are both upper-cased with `O`, `I` and `L` folded onto
  `0`, `1` and `1`, and the search box in the subscription admin applies the
  same normalisation to whatever the operator pastes in.
- **Bulk allotment refuses the whole batch rather than part-filling it.** It
  groups by offering, takes `select_for_update` on the offering row, makes one
  `share_supply()` read for the batch, and refuses everything when the total
  exceeds `min(offering headroom, authorized - issued)`. Allotting a first-come
  subset would destroy the pro-rata fairness that scale-back exists to provide.
- **`reconcile_subscriptions` earns its five-minute slot.**
  `check_executing_issuance_requests` finishes the *request* a killed worker
  left behind; without a mirror on the subscription side the *subscription*
  sits `paid` forever with the shares already on chain. The periodic flips a
  paid subscription to allotted when its linked request reached `executed`, and
  touches nothing else. The daily `expire_unpaid_subscriptions` only ever
  touches a row with no payment recorded against it.
- **Allotment stays an admin action; there is no operator write route.** The API
  carries create, list, detail, submit and withdraw for the investor and nothing
  else, so there is no staff API surface to mis-permission.
- **A subscription is a money record, so its foreign keys are `PROTECT`.** A
  company or an offering that has taken a subscription cannot be deleted, and
  the refusal is a 409 naming how many rows hold it rather than the 503 a raw
  `ProtectedError` produced.
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

- **The register of members is a read-model, and it is complete only while
  allotment is the sole way shares move.** `tokens/services/register.py` reads
  allotments from `ShareIssuance`, confirms every one of those balances with
  `balanceOf` whenever the chain can be reached — the chain wins over the
  allotment record, and a former member whose balance is zero drops off — and
  resolves identity in one query through
  `WhitelistEntry -> Wallet -> UserAccount -> UserProfile`. Four holder types
  come out: `member`, `treasury` from the whitelist label, `ambiguous` where
  two wallets share one address, and `unidentified` where the whitelist can put
  no person behind the address — no entry at all, or an entry whose wallet
  carries no named profile. The last two are two red rows on the console, both
  counted from distinct completed allotment addresses through the same
  `whitelist/services/identity.py` the register uses and with no chain read, so
  the console can never be lower than the register it stands for. No new model,
  no log indexer. **The trigger condition for the Phase 2 indexer is written
  down rather than left as folklore: if the trading write prefixes are ungated,
  or if `resolve_transfer_asset` stops refusing a `tokenized_security`, a
  transferee who never received an allotment becomes invisible and the register
  is wrong from that moment.** That second guard is already conditional —
  `WalletService.broadcast_transfer` runs it only `if token_contract`, so a
  self-signed ERC-20 transfer posted without `tokenContract` reaches the chain
  unchecked; `ShareToken.sol` keeps it whitelist-to-whitelist, but the register
  does not see it. Closing that gap belongs to the transfer path, not to the
  register. Nothing else in Phase 1 depends on the assumption, and nothing
  enforces it but those two guards.
- **The chain read is all or nothing, and the register never quietly loses a
  member.** A single `balanceOf` that cannot be read discards the whole chain
  read for that share class and the register falls back to the allotment record
  for every holder, logged at `ERROR`. It never omits the address it could not
  read, and it never recomputes the percentage column over the survivors: a
  statutory register that silently drops a member on a transient RPC error, and
  then asserts the remaining holders own the rest, is a false record. The
  fallback is stated in the artefact rather than inferred from it — every API
  row carries `source`, the CSV carries a `Balance source` column reading
  `Confirmed on chain` or `Allotment record, not confirmed on chain`, and an
  export that is not chain-confirmed logs a `WARNING` beside the export line.
  `company_stats.totalShareholders` deliberately does **not** run this read.
  `GET /api/v1/companies/{uuid}/stats/` is loaded by the dashboard company page
  and by the mobile company screen, and putting the register behind it would
  put one sequential `balanceOf` per member on a hot path, unbounded and
  uncached, and would make a headline number move with RPC reachability with
  nothing in the payload to say so. The tile stays one `COUNT(DISTINCT
  recipient_address)` over completed allotments: cheap, deterministic, and
  honestly an allotment count rather than a register count — a former member on
  zero is still in it. The register, not the tile, is the statutory artefact.
- **The register export neutralises anything that opens like a formula.** Name
  and residential address come from `users.UserProfile`, which the investor
  sets themselves, and the treasury label from `WhitelistEntry`. Any cell whose
  first character is `=`, `+`, `-`, `@`, a tab or a carriage return is written
  with a leading apostrophe by `shared.utils.csv_cell`, so an issuer opening
  `register-<SYMBOL>.csv` in Excel or Sheets cannot be made to run a formula
  against a sheet of every other member's residential address.
- **Amount paid on the register is blank where it is unknown, never zero, and
  never a part shown as the whole.** It comes from the `Subscription` that
  produced the allotment; a holding that predates the platform has none, and a
  zero would be a false record rather than a missing one. The same reasoning
  settles the mixed row, which is ordinary rather than a corner: a founder
  allotted a thousand shares directly who then subscribes for ten more has
  twenty-five dollars known and a thousand shares unknown, and printing the
  twenty-five beside a holding of one thousand and ten reads as the
  consideration for the lot — a false record that looks authoritative, which is
  worse than a blank.

  The column blanks under any of three conditions, all three spelled out in
  [ARCHITECTURE.md](ARCHITECTURE.md): a share on the row has no subscription
  behind it; the subscribed count disagrees with the balance the row actually
  prints, which is what happens whenever the chain and the allotment record
  diverge; or the money record has not yet caught up with the allotment. The
  figure printed is the consideration for the shares kept, not the cash
  received, so a scaled-back subscription awaiting its refund does not overstate
  what the company is entitled to.

  Showing the known part instead would need a column of its own and a sentence
  saying what it means; neither is worth it in Phase 1. There is no operator
  override field either.
- **The residential address is in the CSV and nowhere else.** The dashboard
  register shows name, holder type and holding. `GET
  /api/v1/tokens/{uuid}/register/export/` writes the s169-shaped CSV. `GET
  /api/v1/tokens/{uuid}/holders/` keeps its path and its four original keys and
  gains `holderType`, `enteredOn` and `shareClass`; both routes are scoped by
  `visible_to_user` and pinned in the cross-tenant route matrix.
- **The export trail is one log line, and nothing more than that.** Each export
  writes an application log line naming the requesting user's primary key and
  the row count. There is no export audit model, nothing queryable, and no
  retention past whatever the deployment keeps its logs for. Every download is
  a full sheet of members' residential addresses, so a durable and queryable
  record of who took one is owed. It is deliberately not built in Phase 1 and
  is not claimed to be: Phase 2 carries it.
- **Past members are not retained, and that is a gap.** The register drops a
  holder whose balance reaches zero, which is right for a list of current
  members. Section 169(3) also wants members who ceased in the last seven years
  kept on the register with the date they ceased. Phase 1 does not meet that
  and nothing here builds it: the read-model has no record of a holding that
  ended, only of allotments that happened. Whether a derived register can
  satisfy 169(3) at all, or whether it forces the Phase 2 `Transfer` log
  indexer and a stored ceased-on date, is the question. Counsel question,
  flagged.
- **The operator console is one page and costs nothing structural.** It replaces
  the dead redirect at `/admin/operators/operator/` — no `AdminSite` subclass,
  no URL namespace, no model. It carries a configuration health strip that
  fails closed before an offering opens rather than at payment-instruction
  time, thirteen worklist counts — eleven linking to a filtered changelist, and
  the two register queues to the unfiltered whitelist changelist, because no
  filter on it expresses their condition and for `unidentified` none could,
  its commonest case being an address with no whitelist row to filter to — and
  the deployment mode with the register keeper named for each active company.
  Every count is a `.count()` or an identity read over allotment addresses; the
  identity read is chunked, so its SQL is the same size on a deployment of ten
  addresses and ten thousand. The page makes no chain call, so it cannot hang
  on a flaky RPC.
- **"Offerings at their cap and still open" counts money in, not allotments
  out.** Decision 8 keeps closing manual and asks the console to catch a fully
  subscribed offering sitting open. The row therefore reads
  `Subscription.paid_or_allotted()`, which is every subscription whose money has
  arrived, rather than B5's `committed_to_shares()`, which additionally requires
  an issuance request and so only fires after the operator has already processed
  the allotment the row exists to prompt. B5's headroom guard is unchanged and
  still reads `committed_to_shares()`.
- **The console states who keeps the register; it does not say who is obliged
  to.** Naming the registrant is a fact about this deployment. Whether that
  party carries the section 168 obligation is a question for the issuer and its
  advisers, and the console says so in as many words. Counsel question,
  flagged.

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
  chain rather than derived from it ad hoc. The Phase 1 register is derived, and
  the trigger for replacing it with a `Transfer` log indexer is written above:
  the moment a share can move by anything other than allotment, a transferee who
  never received one is invisible to it. Two more things wait on the same work:
  section 169(3) retention of members who ceased in the last seven years, which
  a derived current-holders read-model cannot express, and a durable queryable
  record of every register export, which today is one application log line.
- Director authority, ownership immutability, ACN and ABN validation and
  authorized-capital limits, none of which the models check today.

## Phase 3 — Settlement automation

Not started.

- Automate what an operator does by hand now: matching a received payment to a
  subscription, allotting, whitelisting, minting and issuing the confirmation.
  Phase 1 does each of those from the admin with one click; Phase 3 is where a
  bank feed and a chain watcher propose the match instead of the operator
  reading a statement, and where `SubscriptionPayment` earns its place if
  multi-tranche reconciliation is still wanted then.

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
  refuses a `tokenized_security`, and so does `broadcast-transfer`, which no
  longer depends on the caller naming the token contract: an EVM broadcast is
  decoded before anything reaches the chain, and the decode refuses a share
  token target, a foreign chain id, contract creation, and any payload that is
  neither a plain native send nor an ERC-20 `transfer`. The recorded
  `Transaction` row is written from the decoded transaction, not from the
  request body. What also holds the line is on chain:
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
  setting. The period's value is still open and needs counsel; the shape is not.
- **No comments and no docstrings in source.** Settled, and now mechanically
  gated by `make check-comments` rather than held by review alone. See the
  coding rules in [ARCHITECTURE.md](ARCHITECTURE.md#coding-rules).

## Open questions

- Should modifying an order re-run matching automatically? Creating one
  matches; modifying one no longer reports a candidate match.
- `NotificationPreferences` is a separate model that would fold into
  `UserPreferences` with the next settings-screen change.
