# Architecture

How Ledova is put together: the contracts, the backend apps and their layers,
the clients, the shared package, the issuance data flow, the auth and tenancy
models, and the coding rules the repository enforces.

## Pieces

| Path | What it is |
| --- | --- |
| `contracts/` | Solidity sources, Hardhat tests and deployment scripts |
| `backend/` | Django 5 REST API, Django admin, Procrastinate background jobs |
| `dashboard/` | React + Vite web client (operator, issuer and investor screens) |
| `mobile/` | Expo / React Native client |
| `packages/shared/` | `@ledova/shared`: TypeScript constants, types, API services, utilities used by both clients |
| `packages/scripts/` | `generate-css-tokens.mjs`, the CSS design-token generator |
| `marketing/` | Static React + Vite public site |
| `scripts/` | `init-local-env.py`, the local environment bootstrapper, and the gates: `check-comments.py`, `check-layers.py`, `check-logging.py`, with their unit tests in `scripts/tests/` |

## Contracts

All contracts are Solidity 0.8.24 and OpenZeppelin-based. The operator key owns
every one of them.

| Contract | Responsibility |
| --- | --- |
| `WhitelistRegistry.sol` | The allowlist. `addToWhitelist`, `batchAddToWhitelist`, `removeFromWhitelist`, `isWhitelisted`, `canReceive`; owner-only writes, pausable |
| `ShareToken.sol` | One share class. ERC-20 with 0 decimals, burnable, pausable. `authorizedShares` is the cap; `mint` reverts unless the recipient is whitelisted and the cap holds; `_update` blocks any transfer to a non-whitelisted address; `setAuthorizedShares` cannot go below `totalSupply()` |
| `ShareTokenFactory.sol` | `createShareToken(name, symbol, identifier, authorizedShares, owner)` and `getTokenByIdentifier(identifier)`. The identifier is the deduplication key |
| `AtomicSwap.sol` | EIP-712 swap settlement between an approved share token and an approved payment token, executed by an authorised relayer |
| `AUDY.sol` | Minter-gated AUD stablecoin, 2 decimals, used as the payment token. Its `assets.Asset` row plus its `AssetChainDeployment` on the operator's receiving chain are the only representation of a settlement token; `operators/settlement.py` resolves them |
| `AUSG.sol` | NAV-bearing token with a redemption queue; not part of the issuance flow |

`deploy-all.ts` deploys `WhitelistRegistry`, `ShareTokenFactory`, `AtomicSwap`
and `AUDY` and writes their addresses to `.deployed-contracts.env` at the
repository root. `network-safety.ts` refuses any chain id outside
`{1337, 31337, 84532}`.

## Backend apps

One Django app per bounded concern. `backend/ledova_backend/settings/` is a
package of per-concern modules re-exported by `settings/__init__.py`.

| App | Owns |
| --- | --- |
| `operators` | The single `Operator` configuration row, `GET /api/operator/`, and the operator console: `worklist()` and `configuration_health()` rendered by `OperatorAdmin.changelist_view` |
| `authentication` | `CustomUser`, the `AuthViewSet`, JWT sessions, email verification codes |
| `users` | Profiles, accounts, preferences, financial profiles, device tokens, notifications, favourite assets, `InvestorClassification` and the investor-eligibility predicate |
| `companies` | `Company`, its application lifecycle, and company `Document` records |
| `tokens` | `ShareToken`, `ShareIssuanceRequest`, `ShareIssuance`, `CapitalIncreaseRequest`, `MintRequest`, `YieldToken`, and the trading models |
| `offerings` | `Offering`, `Subscription`, their review and payment lifecycles, allotment, and the eligibility-gated investor directory at `/api/v1/directory/` |
| `whitelist` | `WhitelistEntry` and the on-chain allowlist sync |
| `wallets` | `Wallet`, `Holding`, `HoldingSnapshot`, `Transaction`, balance sync and transfer confirmation |
| `assets` | `Asset`, `AssetChainDeployment`, `AssetSnapshot`, `ExchangeRate`, price sync, asset identity |
| `portfolios` | `Portfolio` and the value series computed on read |
| `blockchain` | `BlockchainTransaction` and transaction monitoring |
| `compliance` | Monitoring rules, alerts, procedure templates, risk assessments |
| `documents` | Uploaded documents and their extraction records |
| `integrations` | Chain client, KYC providers, Alchemy, CoinGecko, Blockstream, SendGrid, Transak |
| `feature_flags` | `FeatureFlag` and the trading middleware |
| `shared` | Base model, country lookup, the health-check middleware, the cross-tenant route matrix |

## Backend layers

Most apps are laid out as `models/ querysets/ serializers/ services/ views/
tasks/ admin/`, taking only the layers they need: `operators/` is flat modules,
`integrations/` takes only `admin.py` of those layers (the rest of it is one
subpackage per provider), and `blockchain/`, `compliance/`,
`feature_flags/` and `shared/` are partial. Prefer fewer layers and fewer
lines. Delete before abstracting; add a layer only when a second caller needs
the same logic.

`offerings/` is the reference app for the whole shape: about 924 lines of
service against 138 of view. When a rule below and an existing file disagree,
the rule wins and the file is the backlog.

| Layer | Owns | Never contains | Reference |
| --- | --- | --- | --- |
| `models/` | Fields, `TextChoices`, constraints, `__str__`, properties over own fields, single-row transitions (guard, set fields, `save(update_fields=...)`, at most about ten lines, raising the app's `APIException` on a bad state) | Queries on other models, multi-step workflows, external I/O | `companies/models/company.py` |
| `querysets/` | Every reusable query: `visible_to_user`, `manageable_by_user`, status filters, `select_related` bundles, annotations, aggregates; wired with `objects = XQuerySet.as_manager()` | Saves, side effects, calls into services | `offerings/querysets/offering.py` |
| `services/` | Orchestration across models, external I/O (chain, KYC, email), `transaction.atomic` and `select_for_update`; the one place a multi-model workflow lives. Plain module-level `verb_noun` functions, named after the noun | HTTP objects, serializers, `Response` | `offerings/services/subscription.py` |
| `serializers/` | JSON shape and input validation; writable FKs scoped in `get_fields()` with `visible_to_user` | Business rules, locking, queries beyond FK scoping | `offerings/serializers/subscription.py` |
| `views/` | Permissions, `get_queryset()` returning `Model.objects.visible_to_user(user)...`, serializer choice, one service call, `Response` | Raw `.objects.filter`, try/except that re-wraps an `APIException`, log lines that restate the request | `offerings/views/subscription.py` |
| `tasks/` | `@app.task` / `@app.periodic`: load the row by uuid, call one service, return a dict | Orchestration, state machines | `users/tasks/retention.py` |
| `admin/` | Registration, list/search/filter, operator actions that call the same model transition or service the API calls | A second implementation of a workflow, HTML badge builders | `users/admin/investor_classification.py` |

A service is a module of plain functions. The exception is a stateful client
that holds a connection — the chain clients under `integrations/` — which stays
a class because it has something to hold. A class whose methods are all
`staticmethod` is a module spelled awkwardly: do not add one.

### When not to add a layer

- A service method with one caller that only forwards to the ORM: put the query
  in `querysets/` and call it from the view.
- A queryset method with one call site: inline the filter.
- A base class or mixin for one subclass; an exception class for one raise that
  DRF already covers; a manager for a queryset.
- A task that is never deferred; a periodic task for a one-off backfill (use a
  management command or the shell).
- A model, column or endpoint that records data nothing reads.

## Clients and the shared package

`packages/shared` is consumed from source. `package.json` `main` and `types`
point at `src/index.ts`; there is no build step and no `dist/`. `src/index.ts`
re-exports four sub-barrels: `constants`, `types`, `services`, `utils`.

- The dashboard resolves it through the root npm workspace link
  (`node_modules/@ledova/shared` to `packages/shared`). Vite and `tsc -b`
  follow the symlink to its real path outside `node_modules`, so the sources
  are transformed and type-checked as application code.
- Mobile links it with `"@ledova/shared": "file:../packages/shared"`. Metro
  follows the symlink into `../packages`, which stays in `watchFolders`, and
  `tsc --noEmit` resolves it with `preserveSymlinks`.

Mobile resolves from `mobile/node_modules` and `../packages`, and from nothing
else. `make install` runs the root `npm ci` before mobile's, so the repository
root holds a `node_modules` that Metro's `watchFolders` deliberately excludes —
but TypeScript walks up into it when a lookup fails in `mobile/node_modules`. An
import can therefore type-check against a copy of a package the bundle will never
contain, and `npm --prefix mobile run type-check` stays green while the app
breaks. `mobile/scripts/check-resolution.mjs` closes that: it resolves every
runtime specifier in `mobile/src` the way Node does, honouring each package's
`exports` map, and fails if the answer came from outside mobile or did not
resolve at all. `make check` runs it and CI runs it as its own step. A Node
builtin name that mobile also declares as a dependency (`buffer`, `crypto`,
`stream`) is checked against `metro.config.js`'s `extraNodeModules` instead,
because that alias is what makes it work.

The case that produced it: `@noble/hashes` 2 removed the `./sha256`, `./sha512`,
`./ripemd160` and `./hmac` subpaths that `bip32.ts`, `seedDerivation.ts`,
`localSigner.ts` and `secureKeyStorage.ts` import. Dependabot proposed it, all
four checks passed, and only the root's copy of 1.8.0 made the type-check
succeed. A green type-check is not evidence that mobile resolves.

Every client import is `from '@ledova/shared'`. `packages/shared/src/services`
holds the API call functions both clients share; each takes the caller's axios
instance as its first argument, so the dashboard and mobile keep their own
interceptors.

The design tokens are the single source of colour, spacing and radius values.
`make generate-tokens` runs `packages/scripts/generate-css-tokens.mjs` with
`tsx` over `packages/shared/src/constants/ui/design-tokens.ts` and writes
`dashboard/src/styles/tokens.css` and `marketing/src/tokens.css`, both raw
generator output and prettier-ignored. Tailwind v4 reads that `@theme` block
and derives the utility classes (`bg-surface-base`, `text-text-body`,
`border-border-subtle`). Never edit the two `tokens.css` files: CI regenerates
them after `make build` and fails on any drift.

## Data flow of an issuance

1. An operator or issuer creates a `ShareToken` in `DRAFT` with a name, symbol
   and `total_supply` (the authorized cap).
2. `POST /api/v1/tokens/{uuid}/deploy/` calls
   `ShareTokenService.start_deployment`. It refuses unless the token is `DRAFT`,
   the company is `ACTIVE` and the company has a primary wallet, then moves the
   token to `DEPLOYING` and defers `deploy_share_token_task`.
3. The task calls `getTokenByIdentifier("<acn>:<symbol>")` first. If the factory
   already holds an address, that address is adopted and nothing is sent. The
   ACN is required and unique, so the identifier survives a later ABN, and a
   company can hold several share classes under distinct symbols.
4. Otherwise `createShareToken` is sent, the hash is stored on the token before
   the receipt is awaited, and only a failure *before* any transaction returns
   the token to `DRAFT`. A token whose create transaction was sent stays
   `DEPLOYING` until `check_pending_token_deployments` (every 5 minutes)
   resolves it or an admin uses "Retry Deployment". Deployment mints nothing:
   `totalSupply` starts at zero.
5. An investor wallet is verified, then whitelisted. `WhitelistEntry` either
   points at a `Wallet` or carries a bare `address` plus a `label` for an
   operator-held treasury address; a database constraint requires one of the
   two and makes bare addresses unique.
6. `POST /api/v1/tokens/{uuid}/issue/` creates a `ShareIssuanceRequest`.
   Executing it is refused before any transaction when the recipient is not on
   the `WhitelistRegistry`, the amount would exceed the cap, or the token is
   paused.
7. Execution claims the request with a compare-and-set on its status, so two
   Execute submits cannot both mint. The mint hash is written to the request's
   `ShareIssuance` (idempotency key `issuance-request:<uuid>`) before the
   receipt is awaited, so a retry resumes on that hash: it completes when the
   transaction mined and mints afresh only when it reverted.
   `check_executing_issuance_requests` (every 5 minutes) finishes a request a
   killed worker left executing.
8. A capital increase calls `setAuthorizedShares(new_authorized_total)` and
   mints nothing. It is refused unless the new total is above the cap the chain
   holds now, and increases are serialised per token with a `select_for_update`
   row lock on the `ShareToken` around the cap read, the call and the write, so
   two increases approved against one cap cannot lower it. SQLite ignores the
   lock, which is why CI runs the chain suite on PostgreSQL as well. The same
   `check_executing_issuance_requests` sweep resolves stale capital-increase
   rows, through `resolve_executing_capital_increase`.
9. Pause and unpause read `paused()` first and reconcile the database when the
   chain is already in the target state.

## Data flow of an offering

1. The owner sets `Company.is_open_to_investors` from the dashboard through
   `CompanyUpdateSerializer`. It defaults to `False`, so the directory is empty
   until an owner opts in; the operator can force it off in the admin. It is a
   flag, not a `CompanyStatus`, so a suspension and a reinstatement do not drop
   the listing.
2. The issuer creates an `Offering` against one deployed share class at `POST
   /api/v1/offerings/`, with the price, the bounds in whole shares, the window,
   the exemption relied on, the payment rails and the `CompanyDocument`s to
   attach. Every writable FK is scoped in `get_fields()`.
3. `POST /api/v1/offerings/{uuid}/submit/` calls
   `offerings.services.offering.submit_offering`, the twin of
   `submit_application`. It takes a `select_for_update` on the `ShareToken` row
   first, the way `_execute_capital_increase` does, so the liveness read and the
   status write are serialised per share class and two simultaneous submissions
   produce one submission and one 400 rather than the `IntegrityError` the
   partial unique index turns into a 503. It then refuses unless the token is
   deployed, the company can issue tokens, the share class has no other live
   offering, `cap_shares` fits inside `total_supply` less the completed supply
   less the caps of other live offerings (naming `CapitalIncreaseRequest` in the
   refusal, because `setAuthorizedShares` cannot go below `totalSupply`), every
   settlement asset resolves through `operators.settlement`, at least one
   payment rail is configured, and, for `s708_8_minimum_amount`, the minimum
   subscription is worth at least AUD 500,000.
4. `transition_offering` is the single chokepoint for every status change and
   fires one push to the owner, exactly as `transition_company` does. It is also
   where `approve` re-runs the headroom check, because an issuance completing
   between the submission and the approval shrinks the headroom the submission
   measured; the approval is refused with the same message the submission would
   have used.
5. The operator reviews in the Django admin — start review, approve, reject,
   close. There is no approve, reject or close route on the API at all, so
   there is no staff API surface to mis-permission. The admin cannot rewrite
   what the review is about either: `OfferingAdmin.get_readonly_fields` freezes
   the share class, exemption, price, bounds, payment rails and window on any
   row past `DRAFT` (`LOCKED_PAST_DRAFT`). Freezing them is the whole guard
   rather than repeating the submit checks in the form's `clean`, so there is
   one authority on the economics and no second copy to drift from it.
6. There is no `OPEN` status and no scheduler. Open-now is derived, by
   `OfferingQuerySet.open_now()`: approved, `opens_at <= now`, and `closes_at`
   null or in the future. Nothing can be left in flight, so there is nothing for
   a sweep to fix. Reaching the cap does not close an offering; closing is a
   deliberate operator act.
7. The directory publishes exactly that set and nothing wider.
   `ShareTokenQuerySet.with_open_offering()` annotates from `open_now()`, so a
   submitted or under-review offering is invisible to investors and approval is
   the act that publishes the terms — which is what the admin's approve dialog
   says it does. The annotation carries no status, because only one status can
   ever reach it.
8. `UniqueConstraint(token)` `WHERE status IN (submitted, under_review,
   approved)` allows one live offering per share class. `submit_offering`
   refuses the second submission by name before the write, so the ordinary
   second-tranche path is a 400 that names the offering in flight rather than
   an `IntegrityError`; the constraint stays as the backstop against a race.
   Running two tranches at once needs the constraint relaxed, which is a
   migration.

## Data flow of a subscription

1. An eligible investor creates a draft at `POST /api/v1/subscriptions/`, naming
   an open offering, one of their own verified Base wallets and a whole number
   of shares. Every writable FK is scoped in `get_fields()`: the offering to
   `Offering.objects.open_now()` inside `eligible_investor_companies(user)`, the
   account to the caller's investing accounts, the wallet to
   `visible_to_user(user).verified_evm()` on Base. `create_draft` snapshots the
   offering price onto the row, so a later price edit cannot move a live
   subscription.
2. `POST .../submit/` runs `require_subscription_eligibility(account, company,
   amount_due)`. `accept` in the admin runs it **again**: a certificate can
   lapse between submission and acceptance and the law cares about status at
   acceptance. Both calls name the subscription's own account, never the request
   user's first one, because a user with two investor accounts earns a
   qualification on one and must not spend it on the other.
3. Accepting issues the payment instruction in the same click.
   `offerings.services.payments.generate_reference` builds
   `Operator.payment_reference_prefix` plus an eight-character Crockford base32
   code, retried on `IntegrityError` against the partial unique index.
   `normalize_reference` is applied on generation and on admin lookup, so a
   mangled bank narrative still matches. `build_instruction` returns the
   rail-dependent payload — the operator's bank fields, or the receiving wallet
   plus the settlement asset's contract address and decimals resolved through
   `operators.settlement.require_deployment`, which refuses when the asset has
   no active deployment on `Operator.receiving_wallet_chain`.
4. Payment confirmation is columns on the subscription, not a second model.
   Received equal to due moves the row to `paid`; above due moves it to `paid`
   with a refund owed; below due keeps it `awaiting_payment` unless the operator
   accepts it as final, which scales `allotted_quantity` to
   `floor(received / price)` and records the residual as a refund. On the
   stablecoin rail the transfer hash is required, is normalised to lower case
   and refused unless it is `0x` plus 64 hexadecimal characters, and the partial
   unique index is on `Lower("payment_tx_hash")` — a transaction hash carries no
   checksum case, so the same transfer pasted from two explorers is the same
   transfer and cannot fund two subscriptions. Two operators confirming that one
   hash at the same instant both pass the pre-check, so `confirm_payment` also
   catches the index's `IntegrityError` and turns it into the same refusal the
   pre-check gives, rather than a 500 for whoever loses. The bank rail has no
   such key: settlement there is operator-attested, so a statement line already
   recorded against another subscription is a **warning** on the confirming
   operator's screen, naming the other references, not a refusal. Every money
   action in the admin — acceptance, confirmation, refund, rejection, retry,
   bulk allotment and scale back — writes a `LogEntry`, so a restated
   `amount_received` leaves the earlier figure in the object's history even
   though the column now holds only the latest one; restating downwards warns
   as well.
5. Reject and withdraw are refused while money is recorded and unrefunded, and
   the test is arithmetic, not a flag: `has_money_in` compares `amount_received`
   against the refunds that have actually gone back, so a zero refund closes
   nothing and a partial one leaves the rest held. A refund must be above zero
   and cannot exceed what is still returnable; `refund_amount` accumulates
   across refunds once `refunded_at` is set, and only when every cent is back
   does the row become closeable. Before allotment the whole amount is
   returnable and the refund unwinds the allotment; after allotment only the
   residual that no allotted share paid for can come back — asking for a cent
   more is refused as a claimed mint, because money never leaves while the
   shares it bought stay out. Nothing about the money moves once the shares are
   claimed: recording a refund rejects a
   still-executable issuance request in the same transaction — a compare-and-set
   against `EXECUTABLE_STATUSES`, so the worker's `mark_executing` and the
   refund cannot both win — and a refund, a rejection, a withdrawal or a
   restated payment is refused outright once the request is `executing` or
   `executed`. The status alone is not the test, because `EXECUTABLE_STATUSES`
   includes `failed` and a mint that was broadcast and then lost its receipt
   fails the request with the shares already out. The discriminator the codebase
   already carries settles it: `ShareIssuance.mark_reverted` clears `tx_hash`
   and `mark_failed` keeps it, so a linked issuance with a `tx_hash` means a mint
   is out and every money move is refused by `ShareTokenService.broadcast_mint`
   until the executing sweep resolves it — completing it if it was mined, or
   clearing the hash if it reverted, which reopens the refund. Money never goes
   back while the shares stay out.
6. Allotment reuses the issuance machinery unchanged.
   `ShareTokenService.create_issuance_request` then `request.approve(...)` then
   the `OneToOne` link then a task on the untouched `execute_request`. Three
   existing mechanisms make a double mint impossible and none of them was
   weakened: the `OneToOne`, claimed under `select_for_update` so two
   simultaneous clicks end in one request and one refusal; the unique
   `ShareIssuance.idempotency_key` derived from the request uuid; and the
   compare-and-set in `ReviewableRequest.mark_executing`.
7. The headroom test lives in `allot()`, the exported single-subscription entry
   point, so the offering cap — a disclosure limit, not an internal convenience
   — is guarded however the shares are raised. Bulk allotment groups by
   offering, takes `select_for_update` on the offering row the way
   `_execute_capital_increase` does on the share class, drops the rows `allot()`
   would refuse anyway — already linked to a request, not `paid`, scaled to
   nothing — before it sums, so one stale row in a large selection is refused on
   its own instead of poisoning the batch, makes one `share_supply()` read for
   the batch, hands that headroom down to each `allot()` call, and refuses the
   **whole** remaining batch when the total exceeds
   `min(offering headroom, authorized - issued - unminted)`.
   `totalSupply()` counts what is on chain, not what has already been promised,
   so the chain half of that `min()` also subtracts the shares of every request
   for the token that can still mint — `approved`, `executing`, and `failed`
   while its issuance still carries a `tx_hash`. Without that subtraction two
   sequential batches each fit on their own and jointly do not, and the second
   one ends as a `paid` row whose task refuses forever. Part-filling first-come
   would destroy the pro-rata fairness `scale_back` exists to give. `scale_back`
   itself writes the money it strands: cutting `allotted_quantity` leaves
   `amount_due` and `amount_received` alone by design, so the difference between
   what arrived and what the scaled shares cost is recorded as `refund_amount`
   the same way the partial-payment path records its residual, and the clamp
   floors at zero so a negative headroom scales a row to nothing rather than to
   a quantity the database check constraint rejects.
8. `reconcile_subscriptions` runs every five minutes and is the mirror of
   `check_executing_issuance_requests` on the subscription side: the latter
   finishes the request a killed worker left, and without the mirror the
   subscription sits `paid` forever with the shares already on chain. That sweep
   takes `executing` requests and also `failed` ones whose issuance still carries
   a `tx_hash`, because the last retry of a lost receipt leaves the request
   `failed` with the mint out and nothing else looks at it. The daily
   `expire_unpaid_subscriptions` only touches rows with no payment recorded.
9. Allotment stays an admin action. The API carries create, list, detail, submit
   and withdraw for the investor and no operator write route at all. The issuer
   reads its own offering's subscriptions at `GET
   /api/v1/offerings/{uuid}/subscriptions/`, scoped by the offering's own
   `visible_to_user` and read-only, so payment confirmed and allotment pending
   are visible without emailing support and without a second writable surface.
   `ShareIssuanceListSerializer` carries `subscriptionReference`, so an
   allotment links back to the payment that bought it.
10. `Subscription.offering`, `.user_account` and `.wallet` are `PROTECT`, so a
    money record cannot be destroyed by a cascade. The handler turns the
    resulting `ProtectedError` into a 409 that says how many rows hold the
    target, rather than the 503 a raw database error produced.

## The register of members

The Phase 1 register is a read-model, not a table. `tokens/services/register.py`
holds it, because its subject is one share class and its two callers are the two
`tokens` routes; it reaches `offerings.Subscription` through the reverse
`OneToOne` chain the way `ShareTokenQuerySet.with_open_offering` reaches
`Offering`, so no new app dependency is introduced.

1. Allotments come from completed `ShareIssuance` rows for the share class,
   grouped by recipient address, carrying the earliest completion as the date
   the holder entered the register.
2. Every balance is confirmed with `get_token_balance`. **The chain wins.** An
   address whose allotment record says a hundred and whose `balanceOf` says
   forty-two is on the register for forty-two, and a former member whose
   balance is now zero is off it. Only when no balance can be read at all does
   the register fall back to the allotment record, and it says so in `source`.
   The chain winning the share count is exactly why it also has to win the
   amount paid: a hundred shares' worth of consideration against a balance of
   forty-two would read as the price of the forty-two. Point 5 blanks it.
3. Identity is one query. `WhitelistEntryQuerySet.for_addresses()` plus
   `.with_holder_identity()` resolve `WhitelistEntry -> Wallet -> UserAccount ->
   UserProfile`, and `whitelist/services/identity.py` turns each entry into a
   holder type. The whitelist admin's owner column is the second caller of the
   same pair, so the by-hand walk it used to do is gone.
4. Four holder types come out. `member` is named from the account's profiles and
   carries the residential address; `treasury` takes the whitelist entry's
   label; `ambiguous` is two wallets on one address, which the `OneToOne` on
   `WhitelistEntry.wallet` permits and `WhitelistService._resolve_wallet`
   already refuses to act on; `unidentified` is an address the whitelist cannot
   put a person behind — no entry at all, or an entry whose wallet carries no
   named profile — whose only name is the fallback in
   `ShareIssuanceQuerySet.unique_holders_with_names`. The last two are two red
   rows on the operator console, and they are the only surface that tells the
   operator, who is the only party able to resolve a duplicate wallet. Both
   rows count distinct completed `ShareIssuance.recipient_address` values
   through the same `whitelist/services/identity.py` the register uses, so the
   console and the register never disagree about what a holder type means. That
   identity read is chunked at `ADDRESS_CHUNK` addresses a query, so any one
   query it builds is the same size on a deployment of ten addresses and ten
   thousand. The console makes **no chain read**: it counts allotment addresses, not
   chain-confirmed register rows, so a former member who transferred out and
   was never identified can still be counted. The count is therefore never
   lower than the register's, which is the safe direction for a queue.
5. Amount paid is the consideration for **the shares the row prints**, and is
   **blank** whenever that figure is not exactly known — never zero, never a
   part presented as the whole, and never money the company is holding for some
   other reason. Three things have to line up, and any one of them missing
   blanks the column.

   - Every share on the row is subscribed. A holding that predates the platform
     is unknown, and printing a zero against it would be a false record. The
     mixed row is the ordinary case, not the corner: a founder allotted a
     thousand shares directly who then subscribes for ten more has twenty-five
     dollars known against a thousand shares unknown, and summing only the
     known part against the whole holding reads to an auditor as the
     consideration for all one thousand and ten. `_allotments()` counts the
     completed issuances with no subscription behind them, and one is enough.
   - The subscribed share count equals the balance the row prints. This is
     point 2 arriving here. The chain is what decides the share count, so the
     amount has to be measured against the chain, not against the allotment
     record: a subscription for a hundred behind a `balanceOf` of forty-two is
     blank, and so is a subscription for ten behind a balance of a thousand and
     ten. Guarding the divergence inside the allotment record alone would leave
     the false figure standing on the branch the register prefers.
   - The money record itself stands behind those shares. The figure is
     `Subscription.money_backing_shares` — `allotment_quantity` times
     `price_per_share` — and never `money_held`. A scaled-back subscription is
     why: `scale_back()` writes `allotted_quantity` and `refund_amount` but not
     `refunded_at`, so `refunded_total` and therefore `money_held` stay at the
     full amount received until an operator records the refund, and `allot()`
     does not wait for that. Two hundred and fifty dollars received against
     forty shares kept is one hundred dollars of consideration and a hundred
     and fifty owed back; `money_held` would print the whole two hundred and
     fifty. `money_backing_shares` is zero for any subscription not yet
     `allotted`, which is the window between the issuance completing and
     `_mirror_allotted` catching up, so that too blanks rather than printing a
     nil consideration.

   Showing the known part of a mixed row, or the residual `amount_refundable`,
   would each need their own column and their own sentence here; neither is
   worth one in Phase 1.

`GET /api/v1/tokens/{uuid}/holders/` keeps its path and its four original keys —
`address`, `name`, `balance`, `percentage` — and gains `holderType`, `enteredOn`
and `shareClass`. `GET /api/v1/tokens/{uuid}/register/export/` writes the
s169-shaped CSV, ten columns: Name, Residential address, Wallet address, Holder
type, Class, Shares held, Balance source, Date entered, Whitelist status,
Amount paid. Both are scoped by `ShareToken.objects.visible_to_user` and pinned
in the cross-tenant route matrix. The privacy boundary is deliberate: the
dashboard shows name, holder type and holding, and the residential address
appears in the CSV only. Each export writes one application log line naming the
requesting user's primary key and the row count, and that is the whole of the
trail: there is no export audit model, nothing queryable, and no retention
beyond whatever the deployment keeps its logs for. Every download is a full
sheet of members' residential addresses, so a durable record of who took one is
owed; it is a Phase 2 item, not a Phase 1 claim.

**The register is complete only while allotment is the sole way shares move.**
That holds in Phase 1 because the trading write prefixes are flag-gated and
`resolve_transfer_asset` refuses a `tokenized_security`. The second guard is
conditional and worth stating plainly: `WalletService.broadcast_transfer` calls
it only `if token_contract`, so a client that signs an ERC-20 transfer and omits
`tokenContract` is not refused. `ShareToken.sol` still restricts the recipient
to a whitelisted address, so such a move stays inside the whitelist, but the
register does not see it. Relax either guard — or exercise that gap — and a
transferee becomes invisible, at which point the register is wrong and the
Phase 2 log indexer is owed. [ROADMAP.md](ROADMAP.md#phase-2--eligibility-and-the-register)
carries that as the trigger condition.

Transaction hashes are stored 0x-prefixed. `is_transferable` and
`is_divisible` on `ShareToken` are display-only and have no on-chain effect.

## Auth model

- One authentication class, `authentication.classes.HybridJWTAuthentication`,
  is the DRF default, and `IsAuthenticated` is the default permission.
- Sessions are simplejwt refresh tokens with the `token_blacklist` app. A
  refresh rotates and blacklists the token presented; `signout` revokes one
  session and `signout-all` revokes every session. The access token carries the
  jti of its refresh (`rjti`), and every request checks that session is still
  live, so revocation takes effect on the next request rather than at token
  expiry. An admin email change (`authentication/admin/user.py`) and an account
  deletion (`users/services/lifecycle.py`) revoke every session too; a password
  change (`authentication/views/user.py`) revokes every *other* session and
  keeps the caller signed in, by passing its own `rjti` as `keep_jti`. Both
  tokens default to seven days.
- Two transports. Sending `X-Auth-Transport: bearer` returns the tokens in the
  response body and sets no cookie; without the header the access and refresh
  cookies are set (`httponly`, flags from `settings.AUTH_COOKIE`) and no token
  appears in the body. The dashboard uses cookies, mobile sends the header.
- CSRF applies to the cookie transport only. A cookie-sourced POST, PUT, PATCH
  or DELETE runs DRF's `CSRFCheck` and fails with `403 CSRF Failed`; a Bearer
  request skips it and wins over an `access` cookie replayed beside it. The
  readable `csrftoken` cookie is issued by `auth/verify`, sign-in and email
  verification, and the dashboard's axios client echoes it as `X-CSRFToken`.
- Sign-up requires an emailed six-digit code. The code is hashed at rest,
  expires after ten minutes and is capped at five attempts; sign-in, sign-up,
  verification and resend are throttled per address.
- The Django admin is the operator's console and uses ordinary Django sessions.

## Tenancy model

There is one database and one operator per deployment. Isolation is enforced in
the ORM, not in PostgreSQL: row-level security is not planned.

- Every customer-facing queryset has `visible_to_user(user)` (and
  `manageable_by_user` for writes) that returns `none()` for an anonymous or
  `None` user, and every viewset calls it from `get_queryset`, with one explicit
  exception: the two cross-tenant share-class listings,
  `DirectoryTokenViewSet` (`offerings/views/directory.py`) and
  `TradingTokenViewSet` (`tokens/views/trading_token.py`). Neither is
  owner-scoped and neither ever was, but neither is unscoped either. Both are
  scoped by `users.services.eligibility`, so an ineligible caller gets an empty
  list and a 404 on every detail that is byte-identical to a phantom uuid.
  Neither answers 403, which would confirm the row exists. The market asks
  `investor_eligibility(user)` and returns `ShareToken.objects.none()` when the
  answer is no. The directory asks `eligible_investor_companies(user)` and
  filters on it, because one of the four classification categories is scoped to
  a single issuer: `investor_eligibility(user)` first, and only when that
  refuses, the companies named by the caller's live `associated_person` claims
  that `investor_eligibility(user, company=...)` then accepts. A caller whose
  only live claim is an association with company A therefore sees company A's
  share classes and nothing else, and every other issuer is the same 404 as a
  phantom uuid; a caller with an unscoped claim keeps seeing every listed
  issuer; a caller with neither keeps seeing nothing. The two listings also
  differ in what an eligible caller sees, and deliberately: the directory is
  `ShareToken.objects.in_directory()` — deployed with a contract address,
  company `ACTIVE`, and `is_open_to_investors` set by the owner — because it
  advertises an offer; the secondary market is
  `ShareToken.objects.deployed_with_contract()`, because whether an issuer
  advertises itself has nothing to do with whether its existing holders have a
  market. An `associated_person` claim does not widen the market for the same
  reason: s708(12) is about one issuer's offer, not about a market in shares
  that already exist. `DIRECTORY_ROUTES` and `MARKET_ROUTES` in
  `backend/shared/tests/test_cross_tenant_routes.py` pin both.
- `GET /api/operator/` is the one global singleton route an ordinary caller can
  read, and it is not uniform. Its `payment_instructions` block — bank account
  name, BSB, account number, reference prefix and receiving wallet — is served
  only to staff and to callers `eligible_for_any_company(user)` accepts, which
  is the same predicate the directory is scoped by rather than a second one.
  Everyone else gets the key with `null` in it, which an unconfigured rail set
  is indistinguishable from. The rest of the payload is identical for every
  caller.
- Owner foreign keys are `NOT NULL`, and writable FKs are scoped in
  `get_fields()`.
- Global operator routes require `IsAdminUser`.
- `backend/shared/tests/test_cross_tenant_routes.py` pins the matrix: `ROUTES`
  for detail routes and actions, `OPERATOR_ROUTES` for the admin-only routes,
  `LIST_ROUTES` for collections, and `DIRECTORY_ROUTES` plus `MARKET_ROUTES`
  for the two eligibility-gated listings, which are the one group where a
  foreign row is a 200 for an eligible caller and a 404 for everyone else. A new
  detail route or action gets a row there or a cross-tenant test in its own
  app.
- `deployment_mode` on the operator row (`single_issuer` or `registry`) records
  which shape a deployment is; it does not change the isolation rules.

## Uploaded files

Every uploaded file is private. There is no such thing as a public upload in
this codebase, and `MEDIA_ROOT` holds nothing an authenticated route serves.

- A `FileField` that holds an upload carries `storage=private_storage`
  (`backend/shared/storage.py`) and `max_length=255`, because a private key is
  a uuid path rather than a filename. `PrivateMediaStorage.base_url` is `None`,
  so reading `.url` raises rather than quietly returning a `/media/` path that
  `django.conf.urls.static` would serve to anyone while `DEBUG` is true. The
  three today are `companies.CompanyDocument.file`,
  `documents.Document.file` and `users.InvestorClassification.evidence_file`.
- The upload path names nothing about the uploader. `company_document_path`,
  `document_upload_path` and `investor_evidence_path` all build
  `<owner uuid>/.../<random uuid><ext>`: a leaked key says which row it belongs
  to and nothing else. Never put a primary key, an email address or the
  caller's original filename in a stored key — the original filename lives in
  a column and is handed back in `Content-Disposition` by
  `stream_stored_file(field, mime_type, filename)`.
- The bytes reach a caller through one authenticated action per model, which
  resolves the row through the app's own owner-scoped queryset and then calls
  `shared.views.stream_stored_file`. A foreign row is the same 404 as a phantom
  uuid; an anonymous caller is 401. The serializer's `file_url` is that route,
  never a media path.
- **A streaming admin route is registered with
  `shared.utils.admin_files.admin_file_path`, never with a bare
  `self.admin_site.admin_view(...)`.** `admin_view` checks only that the caller
  is active and staff, which is weaker than the change page beside it: a staff
  account with no model permissions was refused the change page and handed the
  bytes. `admin_file_path` couples the two — it checks
  `has_view_permission(request)` before resolving the row and again with the
  row, and only then streams — so a new file route cannot forget the check
  without abandoning the helper. It answers **403, not 404**: the caller is a
  named staff member who reached the route from the admin, the sibling change
  page already answers 403 for the same row, and hiding a permission gap as a
  missing object would only mislead the operator who has to fix it. Existence
  is not the secret here; the bytes are. Any other custom admin view that acts
  on a row checks the matching permission itself —
  `InvestorClassificationAdmin.transition_view` checks
  `has_change_permission`, because verifying or revoking a wholesale-investor
  claim is a compliance control, not a read. **This is an operational change,
  not only a code one**: a staff account that carried nothing but `is_staff`
  could previously open every one of these routes. Before deploying, grant
  `documents.view_document`, `companies.view_companydocument`,
  `users.view_investorclassification` and `users.change_investorclassification`
  to the operators who need them — the last of those is what verify, reject and
  revoke now require.
- **Uploads are allowlisted at the serializer, not at the reader.**
  `shared.uploads.validate_upload` caps the size and admits only
  `application/pdf`, `image/png` and `image/jpeg` by both content type and
  extension; every upload serializer calls it, including
  `DocumentUploadSerializer`. The stored `mime_type` is the value it returned,
  never `upload.content_type` read straight off the request, because that
  column is echoed back as the `Content-Type` of the streamed response. An
  admin file route streams with `Content-Disposition: attachment` so a row that
  predates the allowlist downloads instead of rendering script on the `/admin/`
  origin; the owner-scoped API route stays `inline`, since it only ever hands a
  caller their own bytes.
- Moving a field onto private storage is one migration per model, shaped like
  `companies/migrations/0006_company_document_private_storage.py`:
  1. `RunPython(move_uploads(..., to_private=True), move_uploads(..., to_private=False))`
     relocates the existing bytes between `MEDIA_ROOT` and `PRIVATE_MEDIA_ROOT`,
     skipping a row whose file is already missing from disk.
  2. `SeparateDatabaseAndState(state_operations=[AlterField(...)])` carries the
     storage and `max_length` change in the migration state only.
  3. `RunPython(widen_char_column(...), noop)` widens the column on PostgreSQL.
  The helpers are in `backend/shared/utils/migrations.py`. **A file move is not
  covered by the DDL transaction, so it undoes itself.** `_relocate` records
  every file it has moved and, when a move raises, puts them all back before
  re-raising: a reverse that dies halfway leaves the whole corpus where it
  started rather than half of it publicly readable under `MEDIA_ROOT` with the
  ledger still claiming the migration applied. That half-moved state was
  unrecoverable by any normal operator action — Django will not re-run an
  operation belonging to an applied migration, so neither `migrate <app>` nor
  `migrate` touches it. Operations still reverse back to front, which puts the
  byte move last on a reverse, so nothing runs after it that could roll the
  database back out from under a move that already succeeded.
  If the put-back itself fails, the migration raises `UploadRelocationError`
  naming every file it could not return, and `manage.py
  reconcile_private_media` repairs the corpus: it walks every `FileField` bound
  to `PrivateMediaStorage`, moves any stored key whose bytes are sitting under
  `MEDIA_ROOT` back under `PRIVATE_MEDIA_ROOT`, drops a public copy that
  duplicates a private one byte for byte, and refuses to guess when the two
  copies differ. `--check` reports without moving anything and exits non-zero,
  so it also works as an audit.
  The widening reverses to a no-op rather than to `AlterField`'s auto-derived
  narrowing, which would raise `value too long for type character varying(100)`
  on any document uploaded after the migration — the generated keys run to 118
  characters. A rollback leaves the column wider than the state claims, which
  costs nothing, and strands no bytes.
  `backend/shared/tests/test_private_storage_migrations.py` round-trips both
  migrations with real bytes, a row whose file is missing, and a key generated
  after the widening, and drives a reverse that fails partway through the byte
  move in both the recoverable and the unrecoverable shape.

## Coding rules

**A rule belongs here only with two things attached: the file that is its
reference implementation, and the gate that enforces it.** A rule that can get
neither is demoted to a documented exception or deleted. This is the standard
this document is being held to, and the sections above now cite a reference for
each layer; the gates are landing behind them.

The reason is stated plainly rather than hidden: most of these rules were held
by review, and a rule held by review means a green pipeline means nobody
checked. Three are gated today — the comment rule through `make
check-comments`, the "one migration per model change" half of the migrations
rule through CI's `makemigrations --check --dry-run`, and the generated design
tokens through the `git diff --exit-code` step (stated under [Clients and the
shared package](#clients-and-the-shared-package)).

A new gate ships with an explicit allowlist of the offenders that exist on the
day it lands, so it is green immediately and blocks only new violations. That
allowlist is the migration backlog made visible, and CI fails if it grows. The
convergence this enables is tracked in
[issue #115](https://github.com/RonildoBraga/ledova/issues/115).

### Why the codebase diverges from these rules

The divergence is generational, not architectural, and knowing that changes
what to do about it. Every one of the 27 `XService` classes dates from the
initial seed commit; every one of the service modules added since is plain
`verb_noun` functions, and none has been added as a class. Post-seed view
modules average about 35 lines, while every view module over 140 lines is
seed-era. `tokens/services/register.py` escapes CSV cells in the service;
`whitelist/views/entry.py` hand-rolls them in the view.

So this is a half-finished migration whose destination already exists in the
tree, not an absent standard. The consequence for how to finish it: **do not
convert the seed-era service classes in a batch.** The direction of travel is
already settled by every commit since; a sweeping rewrite would conflict with
everything in flight and buy nothing the rule below does not. New and touched
service modules are plain functions; the stateful chain clients stay classes;
the rest converts when it is next edited for another reason.

- No Django signals. A side effect is an explicit call in the service (or in
  `perform_create`) that creates the row.
- No new `managers/` packages. The only `Manager` is `CustomUserManager` in
  `authentication/managers/`; everything else is a queryset wired with
  `as_manager()`.
- One `exceptions.py` per app holding only classes that are raised, with no
  `__init__` that merely forwards `detail`. Use DRF's `NotFound`,
  `PermissionDenied` and `ValidationError` for plain 404, 403 and 400. Error
  bodies carry `detail` (auth failures also `error` and `code`); clients read
  `detail`.
- Logging: `logging.getLogger(__name__)`, no prefix constants. Log errors in
  services and tasks, not requests in views. Never log an email address or a
  token: log the primary key instead, which identifies the row for an operator
  without putting a person's address in a log aggregator. On the clients, a
  `console` call takes a message and never an object -- an `AxiosError` carries
  `config.data`, the serialised request body, so logging one prints the password
  a failed sign-in was sent with. `describeFailure` in `packages/shared` turns
  any thrown value into the narrow line worth keeping: status, error code, and
  the method and path with the query string cut off.
  [The logging privacy gate](#the-logging-privacy-gate) below is the mechanical
  half of this rule.
- Constants: `TextChoices` next to the model, numeric thresholds as module
  constants in the app's `constants.py`.
- **No comments and no docstrings in source.** Names and tests carry the
  meaning. There is no "unless it is really needed" clause: wanting to explain a
  line is the signal to rename the thing or add a test, never a licence to
  comment it. `make check-comments` enforces this, and
  [the gate](#the-comment-gate) below is the authority on what it covers. The
  rule covers `backend/`, `dashboard/src`, `mobile/src`, `packages/shared`,
  `packages/scripts`, `marketing/src`, `contracts/contracts`,
  `contracts/scripts`, `contracts/test`, and the root build config of
  `dashboard/`, `marketing/`, `mobile/` and `contracts/`, each by the extensions
  the gate lists. The root `scripts/`
  tree is outside them: every file there carries a module docstring. The only comment
  lines permitted are functional directives the tooling reads: `# noqa`,
  `# type:`, `# pragma`, `# fmt:`, `# isort` and the shebang/coding lines in
  Python; `eslint-disable`/`eslint-enable`, `@ts-ignore`/`@ts-expect-error`/
  `@ts-nocheck`, `prettier-ignore`, `/// <reference`,
  `@vitest-environment`/`@jest-environment`, `istanbul`/`c8`/`v8` coverage
  pragmas, `/* global */` and `biome-ignore` in TypeScript and JavaScript; and
  `// SPDX-License-Identifier` in Solidity. That list is closed: a directive not
  on it is a comment, however useful it looks. No section banners, no
  Args/Returns blocks, no `help_text` that restates a field name, and no note
  explaining a swallowed error — `no-empty` carries `allowEmptyCatch: true` in
  the dashboard, mobile and `packages/shared` ESLint configs precisely so an
  ignored `catch` can stay empty. Configuration and documentation files
  (`.env.example`, YAML, Makefiles, Dockerfiles, Markdown) are documentation and
  keep their comments.
- Tests: `APITestCase` under `<app>/tests/`, superusers via `create_superuser`.
  `make test` runs on SQLite; CI also runs the migration-stage tests and the
  whole suite on PostgreSQL.
- Client tests: every JavaScript workspace has a runner and CI runs all of them
  through `make test`. `packages/shared` and `mobile/` use Jest, the dashboard
  uses Vitest, `contracts/` uses Hardhat. Mobile's config is `mobile/jest.config.js`
  (the `jest-expo` preset); its tests sit beside the code they cover as
  `*.test.ts`/`*.test.tsx`, the same convention the dashboard follows, so the
  comment gate reaches them and they carry no comments either.
  `mobile/src/hooks/useFeatureFlags.test.tsx` is the reference: it mounts the
  hook with `renderHook` from `@testing-library/react-native` — asynchronous
  since version 14, so it must be awaited — over a `QueryClientProvider`, and
  mocks `../services/apiClient` rather than the `@ledova/shared` service that
  calls it. A test must leave no promise pending when it ends: a request stubbed
  with a promise that never settles keeps Jest alive after the run reports
  success, so stub with a deferred you resolve before the test returns.
- The dashboard smoke: `dashboard/tests/smoke/*.smoke.ts` drives a real Chromium
  against the built bundle, and `make smoke` runs it in CI on every pull request.
  It answers one question — does the shipped bundle boot and route without
  throwing — so it stubs `**/api/**` with a 401 instead of expecting a backend.
  The console-error assertion filters exactly the noise that stub provokes and
  nothing else, which is what keeps it able to fail: an uncaught exception from
  the bundle still ends up in the same list. A smoke test never depends on the
  API, the database or the chain; anything that does belongs in the Django suite
  or `make chain-test`.
- Migrations: one per model change, never edit an applied one. On testnet an
  unapplied one may be deleted.
- Dependencies: nothing in `requirements.txt` or a `package.json` without an
  importer.
- Endpoints: nothing routed without a caller in `dashboard/`, `mobile/`,
  `packages/`, a documented external consumer, or the operator API. Check
  `packages/shared` before concluding a route is dead: `POST
  /api/wallets/batch-check-balances/` looks unreferenced from either app but is
  called through `packages/shared/src/services/wallet-balances.ts`, which the
  dashboard's add-wallet modal and the mobile balance hook both use.
- The operator API is the named exception: `IsAdminUser`-gated routes an
  operator drives from a script or a client the repository does not ship. The
  whole `/api/v1/whitelist/` tree (`whitelist/urls.py`) and
  `/api/portfolios/{uuid}/add-wallet/` and `/remove-wallet/` are in it. They
  have no caller in either app and are kept, tested and documented deliberately.
- The dashboard, the mobile app and `packages/shared` are first-class clients:
  every response key, status code and URL they read is a contract the backend
  keeps.

[CONTRIBUTING.md](../CONTRIBUTING.md#gates) lists the commands that gate a pull
request, and which of them CI does not run for you.

### The comment gate

`scripts/check-comments.py` is the mechanical half of the no-comments rule.
`make check-comments` runs it, `make check` includes it, and CI runs it as its
own job. It needs no dependencies and no installed environment: Python 3 and a
checkout are enough.

It parses rather than greps. A `//` inside a URL string, a regex literal like
`/^[mM]\//`, and a URL or an apostrophe in JSX text are not comments, while a
`/* ... */` inside a `${...}` substitution or a `{...}` JSX expression is one.
`.tsx` and `.jsx` are scanned with a JSX mode, so a closing tag does not hide
the rest of its line. Python goes through `tokenize` for comments and `ast` for
docstrings, which also catches a bare string statement sitting where a docstring
would.

What it covers, by extension: `.py` and `.css` under `backend/`; `.ts`, `.tsx`,
`.js`, `.jsx`, `.mjs` and `.cjs` in the client, shared and contract-script
trees, plus `.css` in `dashboard/src` and `marketing/src`; `.sol` under
`contracts/contracts`. The build configuration at the root of `dashboard/`,
`marketing/`, `mobile/` and `contracts/` is covered too, but only at that root,
not recursively. `TREES` at the top of the script is the machine-readable copy
of that list — change it and this section together.

One thing sits outside it: the admin templates under `backend/*/templates/` are
not checked. They carry no comments today; keep it that way.

A green CI run is evidence for the trees in `TREES` and nothing else.

### The layer gate

`scripts/check-layers.py` is the mechanical half of the "Never contains" column
of the layer table above. `make check-layers` runs it, `make check` includes it,
and CI runs it in the same job as the comment gate. Like that gate it needs only
Python 3 and a checkout. `backend/shared/tests/test_layer_gate.py` pins each
rule against a snippet, so the decisions below are executable rather than prose.

Every offender that existed when the gate landed is listed in `LEGACY`, which is
the migration backlog made visible. It only shrinks: an entry that no longer
violates anything is reported as stale and fails the run, so the list cannot
outlive the problem. `python3 scripts/check-layers.py --show-legacy` prints it
with line numbers. Move the logic rather than adding an entry.

Two calibrations are worth stating, because both times the gate was wrong and
both times the tell was the same — one shape appearing in several files at once.

- **`transaction.atomic` in a view.** `@transaction.atomic` decorating `create`,
  `update`, `partial_update` or `destroy` says *this whole generic operation is
  atomic*, and the row lock belongs in `get_queryset` where DRF fetches it. That
  is allowed. `with transaction.atomic():` in a body, or the decorator on a
  `perform_*` hook, says *I am orchestrating*, and orchestration is the
  definition of a service. That is flagged. The distinction is syntactic and
  sharp, and sharpening it caught more real workflows, not fewer.
- **A query in a model.** The rule is *queries on other models*, so the gate
  compares the receiver: `cls.objects`, `self.objects` and the model's own class
  name are its own manager and are allowed, which is what makes a lazy singleton
  accessor like `Operator.get()` or `Country.get_or_create_for_code()` legal
  where it stands. Any other model's manager is flagged, whether it sits in a
  transition, a derived property or a `@classmethod` finder, and belongs in a
  queryset or a service.

The general form: when a rule flags the reference app, or the same shape in
several files at once, the rule is wrong and the fix is to sharpen it. Never
excuse a file into `LEGACY` to make a number go down.

### The logging privacy gate

`scripts/check-logging.py` is the mechanical half of "never log an email
address or a token". `make check-logging` runs it, `make check` includes it, and
CI runs it in the source-gates job. Like the other two it needs no dependencies:
Python 3 and a checkout are enough. `make test-gates` runs its unit tests in
`scripts/tests/`, which is the evidence that it fires rather than merely runs.

It enforces three rules, each chosen because it is decidable from the syntax
alone. A gate that has to guess what a value holds at run time is a gate that
gets allowlisted into meaninglessness.

Clients -- `dashboard/src`, `mobile/src`, `packages/shared/src` and
`marketing/src`, by the same TypeScript and JavaScript extensions the comment
gate uses. Every argument of `console.assert`, `console.debug`, `console.dir`,
`console.error`, `console.info`, `console.log`, `console.table`,
`console.trace` and `console.warn` must be one string literal or one template
literal, and no template may reach for `JSON.stringify`. The guarantee that buys
is total: the only thing such a call can emit is what template stringification
produces, and `String(axiosError)` is the error's message, never its request.
An argument that is a plain string variable is refused too. That is the price of
the rule being decidable, and the fix is to inline it into the template.

Backend -- every `.py` under `backend/`. No call on a `logger`, `logging` or
`log` object may reference an email address, a password or a push token, where
"reference" means an expression whose own syntax names one: the attribute
`.email`, `.password` or `.push_token`; a bare name `email`, `password` or
`push_token`; or a constant string subscript with one of those keys. Positional
arguments, keyword arguments and f-string substitutions are all walked.

Backend, second rule -- no logging call may hand a whole provider response body
to the formatter. Naming a field is a decision about what an operator needs; a
whole body is whatever the provider chose to send, and for a KYC provider that
is the applicant dossier: legal name, date of birth, residential address,
document number, email address. The syntax that says "whole body" is a bare
name from the gate's `BODY_NAMES` (`response`, `payload`, `body`, `data`,
`result`, `error_body`, `webhook_data`, `applicant_data`, `status_data` and the
rest), a `.text`, `.content`, `.data`, `.details` or `.body` attribute, a
`.json()` call, or a constant subscript or `.get()` of one of those keys --
reached directly or through `str()`, `repr()`, `json.dumps()` or `.format()`.
The rule looks only at the value handed to the formatter, so
`f"{response.status_code}"` and `f"{ticket.get('id')}"` are fine and
`f"{response}"` is not. `SumSubService.get_applicant_data` and
`get_applicant_status` log the applicant id and the review answer, which is
what `IdentityVerificationService.get_verification_status` polls them for;
`ExpoPushClient` logs the Expo error code rather than the ticket, whose
`message` and `details` both echo the push token.

What it does not cover, deliberately. `print` and a management command's
`self.stdout.write` are ungated: the only `print` calls in `backend/` are the
progress counters in `assets/migrations/0009_...`, and no command writes an
address. An object whose `__str__` returns an email -- `CustomUser.__str__`
does -- is ungated too: `f"{user}"` in a log line is a leak the syntax cannot
tell apart from `f"{token}"`, and no site does it today. `contracts/`,
`packages/scripts/` and the root build config of each client are outside the
client trees; they are build tooling that never holds a user's request. The
client scanner lexes strings, templates, comments and regex literals so that a
`console.error(` inside any of them is not a call, but it has no JSX mode: an
apostrophe in JSX text can hide the rest of that line from it. Console calls sit
on their own lines, so that costs nothing today, and a call hidden that way
would be a false negative, never a false positive. Nor does anything reach the
content of a string field: a provider's own error message -- Expo's is
`"ExponentPushToken[...]" is not a registered push notification recipient
device` -- is a `str` like any other, so `ticket.get('message')` is refused
only by review, not by the gate. The same holds on the clients, where the
literal-only rule certifies a template whatever it interpolates:
`mobile/src/components/ErrorBoundary.tsx` logs `error.message` and
`info.componentStack`, and
`mobile/src/screens/signup/identity-verification/components/VerificationFormModal.tsx`
logs the `message` of a WebView `postMessage`. Both are provider- or
SDK-authored strings today; if one ever carries user input, the gate will not
say so.

### Shared TypeScript types

`packages/shared/eslint.config.js` applies `eslint-naming-rules.js` to
`src/types/**/*.ts`. Two rules are live there. The naming-convention rule is an
error:

- Interfaces and type aliases are `PascalCase`, no underscores. The custom
  regex is `^[A-Z][a-zA-Z0-9]*$`, so a digit anywhere after the first character
  is fine (`EIP712Domain` in `src/types/domain/trading.ts` passes).
- Properties are `camelCase`, except the query-parameter and API-field names
  listed in the rule's filter (`page`, `page_size`, `order_by`, `start_date`,
  `end_date`, `min_*`, `max_*`, `is_*`, `has_*`, `*_uuid`, `*_id`, `*_at`,
  `*_type`, `*_status`, `contract_address`, `user_account` and the rest).
- Enum members are `UPPER_CASE` or `PascalCase`.

The query-parameter rule is a warning: inside a `*QueryParams` or `*Filters`
interface, `minValue`, `maxValue`, `startDate`, `endDate`, `searchQuery`,
`orderBy` and `pageSize` warn, because query parameters use snake_case to match
the URL.

Two conventions in the same file are **not** enforced. Prefer a utility type
over the entity to a `*Payload`, `Create*` or `Update*` interface, for example
`type CreateEntity = Omit<Entity, 'uuid'>`; the `Signin`, `Signup`,
`EmailVerification`, `TokenRefresh` and `GenerateDocument` payloads are the
intended exceptions. `eslint-naming-rules.js` does declare
`noEntityPayloadRule` and `useUtilityTypesRule` for these, but all three
restricted-syntax rules use the same `no-restricted-syntax` key and the object
spread building `namingConventions` keeps only the last, so only the
query-parameter rule reaches eslint. `CreateFavouriteAsset`,
`UpdateUserPreferences` and `CreateOrderRequest` already lint clean under
`src/types/`. Fixing that means merging the three selectors into one
`no-restricted-syntax` entry, then cleaning up what it flags: a code change,
not a documentation one.

Naming patterns the existing types follow: an entity is the bare name (`Asset`,
`Wallet`, `Portfolio`, `UserProfile`); a query-parameter interface is
`{Entity}QueryParams`; a non-CRUD request is `{Action}Request` and its reply
`{Action}Response`. Compose query parameters from the base types in
`packages/shared/src/types/api.ts` rather than repeating their fields:
`PaginationParams` (`page`, `page_size`), `LimitParams` (`limit`, `offset`),
`OrderingParams` (`order_by`), `DateRangeParams` (`start_date`, `end_date`),
`BaseQueryParams` (pagination plus ordering) and `TimeSeriesQueryParams`
(limit, ordering, date range plus `max_points`).
