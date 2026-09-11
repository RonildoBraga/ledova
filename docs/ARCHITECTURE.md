# Architecture

How Ledova is put together: the contracts, the backend apps and their layers,
the clients, the shared package, the issuance data flow, the auth and tenancy
models, and the admin and identifier surfaces.

The rules and the gates that enforce them are in [GATES.md](GATES.md); the
failures behind them are in [TRAPS.md](TRAPS.md); how work is done is in
[PRACTICES.md](PRACTICES.md).

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
| `models/` | Fields, `TextChoices`, constraints, `__str__`, properties over own fields, single-row transitions (guard, set fields, `save(update_fields=...)`, at most about ten lines, raising the app's `APIException` on a bad state) | Queries on other models, multi-step workflows, external I/O | `offerings/models/offering.py` |
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

Mobile transport, device-only session/seed storage and generated native build
policy are described in [MOBILE.md](MOBILE.md). The native probe uses a separate
entry and isolated synthetic servers; it is not part of the application flow.

Mobile resolves from `mobile/node_modules` and `../packages`, and from nothing
else. `make install` runs the root `npm ci` before mobile's, so the repository
root holds a `node_modules` that Metro's `watchFolders` deliberately excludes —
but TypeScript walks up into it when a lookup fails in `mobile/node_modules`. An
import can therefore type-check against a copy of a package the bundle will never
contain, and `npm --prefix mobile run type-check` stays green while the app
breaks. `mobile/scripts/check-resolution.mjs` closes that: it resolves every
specifier the way Node does, honouring each package's `exports` map, and fails if
the answer came from outside mobile or did not resolve at all. `make check` runs
it and CI runs it as its own step.

It scans what Metro bundles, which is `mobile/src` recursively **and the entry
chain at the mobile root** — `index.ts`, `App.tsx`, `crypto-polyfill.js`. A root
file named `*.config.*` runs in Node rather than in the bundle and is skipped.
The entry chain is not an afterthought: eight declared dependencies, all of them
polyfills and shims that Dependabot bumps as majors, are imported only there.

Naming the skip by convention rather than following the import graph from
`package.json` `main` is deliberate, and the reason is which way each fails. A
root file that Metro does not bundle and is not called `*.config.*` gets scanned
and may fail on a Node-only import — a false positive, loud and fixed by renaming
the file. A graph walk fails the other way: a bundled file the traversal never
reaches is silently unscanned, which is the single thing this gate exists to
prevent, and `crypto-polyfill.js` is exactly that shape — pulled in for its side
effects rather than imported from the entry. For a gate, prefer the failure that
shouts. The same rule decides everything else here: an empty `testMatch` makes
the script refuse to run rather than treat every file as a test.

The workspace-wide self-import rule lives in `scripts/check-self-imports.mjs`,
run by `make check-self-imports`, `make check` and its own CI step. Each
package manifest under `packages/` supplies its name. The whole package,
including tests, is checked for imports of that name or its subpaths. Those
imports can resolve back through Metro's aliases and create a cycle in either
client; use a relative path within the package.

Both this rule and mobile resolution read source imports through the TypeScript
parser in `scripts/source-imports.mjs`. Import declarations, re-exports,
`require`, dynamic imports and import types count. Quoted examples, comments,
regular expressions and JSX text do not. The shared parser uses the compiler
already declared by each consuming workspace. The self-import gate no longer
lives inside the mobile resolution script.

The extension list matches the comment gate's client-source extensions. The
resolution check still scans bundled entry files and workspace source; tests
are included in the separate self-import check.

A specifier whose package is not in `dependencies` **fails**, rather than being
skipped. Skipping it was the second hole: a package that exists only in the
repository root resolves for TypeScript through the walk-up above and does not
exist for Metro, which is the exact case this gate is for. The one exemption is a
`devDependencies` package imported from a test file, as `jest.config.js`
`testMatch` defines test files — and the same import from bundled code fails.

A Node builtin name that mobile also declares as a dependency (`buffer`,
`crypto`, `stream`) is checked against `metro.config.js`'s `extraNodeModules`
instead, because that alias is what makes it work.

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
   and `total_supply` (the authorized cap). The historical API key `totalSupply`
   represents this same cap; `issuedSupply` and the contract's `totalSupply()`
   represent shares actually issued. Shares use whole units: model validation
   and the `share_token_whole_units` database constraint require
   `ShareToken.decimals` to be zero, matching the contract. Settlement assets
   retain their own decimal precision.
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
   A requested total at or below the stored cap becomes `superseded` before
   resuming or sending. This is terminal: the saved reason names both totals
   and the completed request that set the current cap when known, and asks for
   a new request. Human review notes survive. The sweep rechecks the cap and
   request status under the same lock after reading a receipt, so a delayed
   result cannot overwrite a later cap or reopen a terminal request.
9. Pause and unpause read `paused()` first and reconcile the database when the
   chain is already in the target state.

Review and execution notes have separate ownership. Reviewers write
`review_notes`; execution attempts append timestamped entries to
`execution_notes` in the database, so an older request object cannot overwrite
an intervening attempt. Successful execution adds its outcome after earlier
refusals. The operator view places this history in the Execution section.
Reviewer notes are internal operator audit text and are omitted from issuer
serializers. Issuers receive execution notes and rejection or supersession
reasons. Provider diagnostics remain in the operator records and logs; a failed
execution asks an operator to check the chain before deciding whether to retry.

Issuers read their requests through `GET /api/v1/tokens/issuance-requests/`,
filtered by token, company or status. List and detail reads retain company
ownership checks even when the database allows a subscriber to read the linked
request for withdrawal checks. The endpoint is read-only. The dashboard token
modal refreshes this history after a successful submission, pages through older
requests and offers retry on loading errors. Execution notes remain visible;
private review notes are absent from both the API and its client type.
Submitting an approval request writes database state without opening a chain
connection; chain checks belong to execution of an approved request.

The execution-history migration preserves every existing review note verbatim.
It cannot establish authorship from phrases such as "Execution failed", which
a reviewer could also have typed. It adds fixed context identifying old notes
as historical and the request status as the current outcome. It does not
reconstruct overwritten reviewer notes or infer missing execution events.

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
   `shared.payment_references` derives the prefix ceiling from the 18-character
   field budget minus the eight-character code. Generation refuses an overlong
   normalized prefix even when a write bypassed model validation; it never
   truncates the random code. Existing references and field widths are unchanged.
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
   pre-check gives, rather than a 500 for whoever loses. The hash is required,
   format-checked and enforced unique, but **not verified against the chain**:
   `confirm_payment` never asks whether that hash exists, moves the right
   amount, or reaches the operator's wallet. For an operator transcribing a
   transfer from a block explorer that is a defensible trust boundary — the
   operator is trusted throughout this admin — but it does mean a stablecoin
   payment is confirmed on the operator's word, exactly like a bank transfer.
   The bank rail has no such key: settlement there is operator-attested, so a
   statement line already recorded against another subscription is a
   **warning** on the confirming operator's screen, naming the other
   references, not a refusal. Every money
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
s169-shaped CSV, twelve columns: Name, Residential address, Wallet address,
Holder type, Class, Shares held, Percentage of issued supply, Balance source,
Identity source, Date entered, Whitelist status, Amount paid. Both are scoped
by `ShareToken.objects.visible_to_user` and pinned in the cross-tenant route
matrix. The privacy boundary is deliberate: the
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

### The register cannot be deleted through the API

The spine that carries the register is `Company -> ShareToken -> {ShareIssuance,
ShareIssuanceRequest, CapitalIncreaseRequest, Offering, TransferOrder}`, and
every one of those relations is `PROTECT`, for the reason
`Subscription.offering` already was: a statutory record must not be destroyed as
a side effect of deleting its parent. Before this, nine `CASCADE` edges were
reachable from one company row, and an issuer with delete permission on its own
company could take the whole s169 register and the issuance trail with it.
`TransferOrder.token` is on that list although the original audit missed it: a
settled order is a share movement with an on-chain hash, and the same argument
that keeps an allotment keeps it.

`SwapOrder.share_token` is `PROTECT` too, and the argument for leaving it
`CASCADE` is recorded here because it was made and it was wrong. It said a
`PROTECT` there would be refused by `TransferOrder.token` first and add nothing,
since a swap's `sell_order` and `buy_order` are both non-nullable. That holds
only while those orders point at the same share class as the swap does, and
nothing enforces that they do. Repoint them and the swap contributes no
protection of its own, so a class whose sole dependent was a settlement record
would delete and take it. A swap is the row that says shares actually changed
hands; it protects the class itself rather than inheriting protection from its
two orders.

The application evidence edges below the company remain `CASCADE`.
`CompanyDocument.company` carries listing evidence the issuer already creates
and deletes through `DELETE /api/v1/companies/{uuid}/documents/{uuid}/`, so it
is not a register row. `CompanyRegistryCheck.company` carries the review's ABR
attempts and is removed when a company with no share classes is deleted. Its
PostgreSQL foreign key cascades in the database because the application's role
cannot read operator-only history for Django's deletion collector. This does
not grant that role access to registry attempts. `OrderModificationLog.order` and
`SwapOrder.sell_order`/`.buy_order` are subordinate to an order that can now
only be deleted deliberately, never by deleting the share class above it.

`CompanyViewSet.perform_destroy` calls `companies.services.company.delete_company`
and `ShareTokenViewSet.perform_destroy` calls
`tokens.services.share_token_service.delete_share_token`. Both refuse with **409
Conflict** — the caller is authorised and the request is well-formed, and it is
the state of the resource that conflicts, which is the same reading and the same
status `shared/api/exceptions.py` already gives a raw `ProtectedError`.

**The two routes ask one question, and the question is `contract_address`, not
`status`.** `ShareToken.is_on_chain` and `ShareTokenQuerySet.on_chain()` are that
question; a class with an address has been on chain and is a register of members
whatever its status reads. Two predicates for one invariant is what let the first
bypass through, and status alone reopens it: a **paused** class is on chain with
its holders intact, and `is_deployed` — `status == DEPLOYED and contract_address
is not None` — is false for it. Do not reach for `is_deployed` or `deployed()`
here; they answer a narrower question, about what the class is doing now rather
than whether it exists on a chain.

A company holding an on-chain share class is refused and told to delist. A
company whose classes are all still drafts is refused too, by the route and not
by the collector, and told to delete them first: a draft is not a register, so
"referenced by rows that must be kept" was the wrong sentence for it, and half a
rule enforced by a generic handler is not a rule. A company with no share classes
is deletable. Delisting is the operator's archive path and it already exists;
test data is removed through the Django admin, share class first. No new archive
model was built for this. The `PROTECT` edges stay the backstop under both
refusals, for the shapes neither route anticipated.

`WhitelistEntry.wallet` is still `CASCADE`, deliberately and for now. Deleting a
wallet deletes the whitelist entry, and since point 3 resolves holder identity
through that entry, a named member on the register silently becomes
`unidentified`. That is a real defect and it is not fixed here.

Two attempts at it failed review, and the reason is worth recording so the third
does not repeat them. `SET_NULL` alone is worse than the `CASCADE`: an entry with
no wallet is the treasury shape, so the member is relabelled the company's own
treasury. Carrying the identity on the entry instead — a stamped address and a
holder reference — moves the failure rather than removing it: re-registering the
same address makes a second entry, and two entries at one address render as
`ambiguous`, so the name is still lost; and editing an unverified wallet's
address leaves the entry stamped with the dead one, so the row disappears from
the register entirely. Both are reachable by an ordinary member with two API
calls.

What that says is that the identity of a holder does not belong on the whitelist
entry at all, because the entry is a chain allowlist record with its own
lifecycle. Preserving identity across a wallet deletion needs the ownership
ledger this is all heading towards, where a holder is named by the event that
gave them shares rather than by whatever allowlist row happens to survive.
Tracked as issue 158, with both failed designs and the probes that broke them.

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

### Client session queries

`packages/shared/src/hooks/useAuth.ts` owns the authentication query and exports
`AUTH_QUERY_KEY`. Each client supplies its API instance through
`ApiClientProvider`; focus and reconnect behavior comes from that client's
`QueryClient`. The dashboard uses focus and reconnect revalidation. Mobile
keeps focus revalidation disabled and rechecks on reconnect. Authentication
does not automatically retry a failed request, but a later mount may recheck a
previous failure; the dashboard's former `retryOnMount: false` no longer keeps
that failed answer in place.

The hook exposes fetching separately from the first session check. A retry after
a completed failure does not restore initial loading: public forms keep their
nested auth consumers mounted, so another failure cannot create a remount loop.
The dashboard's
protected route waits while a cached negative is being rechecked, keeps
protected content hidden until a positive answer, and redirects after a
negative answer or failure. Signup completion still awaits its explicit auth
refresh before navigating. `packages/shared/tests/hooks/useAuth.test.tsx` and
the dashboard's `ProtectedRoute.test.tsx` cover these policies.

Both clients use the shared `useUserPreferences` and `useCurrency` hooks.
Preferences and exchange-rate queries start only after authentication; cached
preferences are hidden again when authentication is lost. Mobile now applies
the same authentication gate to exchange-rate requests as the dashboard.
Currency display keeps the AUD fallback, USD identity conversion and an
unavailable marker when a required rate cannot be read.

## Tenancy model

There is one database and one operator per deployment. Isolation is enforced in
the ORM today, and PostgreSQL row-level security is being added underneath it in
stages, tracked on [issue #115](https://github.com/RonildoBraga/ledova/issues/115).
The ORM rules below are the live mechanism and stay the live mechanism; RLS is a
second floor under them, not a replacement.

**Stage R0 — the owner column.** A table whose owner is reachable only through a
parent cannot be read by a policy without a join, so each such table gains a
direct owner column. The shape is the same every time and is stated here once so
each lane does not re-derive it:

- The column is added **nullable**, backfilled from the parent link, altered to
  **`NOT NULL`**, and indexed by Django's own foreign-key index. `related_name`
  is `"+"`, because the column exists for a policy to read rather than for
  anyone to traverse: no reverse accessor appears and no queryset changes
  shape. **How many times the backfill writes each row is the thing to know
  about it**, and it is not the same question as how many statements it runs.
  One `UPDATE` per table is the usual shape and writes each row once;
  `tokens/0023` fills `signing_challenges` with a bulk `UPDATE` and then a loop
  over the rows it left, several statements over disjoint rows and still one
  write each; and it writes `tokens_swaporder` twice, once per owner column,
  which is the case the settle bullet exists for.
- **`on_delete` mirrors the strictest `on_delete` on the path it derives from.**
  A shortcut to an owner must not make that owner deletable when the path it
  replaces refuses. `Subscription.company` and `Offering.company` are `PROTECT`,
  because `Offering.token` and `ShareToken.company` are; the users columns and
  `Transaction.user_account` are `CASCADE`, because their whole path cascades.
  Django enforces `on_delete` in the collector rather than in DDL, so this is
  ORM consistency rather than a schema difference — which is exactly why it has
  to be chosen deliberately: nothing in the database will contradict a wrong
  choice. **A path of more than one hop takes the strictest `on_delete` of
  every hop, not of the last one.** `SwapOrder.seller_wallet` derives through
  `sell_order` (`CASCADE`) and then `TransferOrder.wallet` (`PROTECT`), so the
  column is `PROTECT`: the shortcut must refuse whatever any hop of the path it
  replaces would refuse. Copying a neighbouring lane's `on_delete` without
  walking the path is how all four `tokens` columns were `CASCADE` in their
  first revision.
- **A parent reachable only by value keeps the column nullable for the rows
  that cannot be resolved.** `SigningChallenge.order` is legitimately null — an
  `ORDER_CREATE` challenge is issued before the order exists — so those rows
  reach their wallet only through `wallet_address`, and `Wallet.address` is
  unique per `(user_account, address)` rather than globally. An address held by
  two accounts is **ambiguous**, not a coin toss: it stays `NULL` and is
  counted separately from orphans in the migration's output. The column is
  nullable for the rows already written; the trigger refuses a `NULL` on
  insert, so nothing new arrives without one. A table can be mixed, and each
  row derives through whichever link it has.
- **A child whose parent already carries the owner column derives from the
  parent**, not by re-walking to the root, so every trigger stays a single join.
  That makes the backfill order load-bearing when a lane has both, and it is the
  one place where the backfill's own "no owner" guard is reachable rather than
  defensive.
- The **trigger is installed last**, so the column is already constrained before
  the trigger exists. It is `BEFORE INSERT OR UPDATE`, PostgreSQL only — SQLite
  has no plpgsql and nothing there for it to protect — and it derives a missing
  owner from the parent, refuses a value that does not match the parent, and
  refuses an update that changes one already set. Filling a NULL is the change
  it exists to make, so the immutability guard reads `OLD IS NOT NULL AND OLD <>
  NEW`; `IS DISTINCT FROM` makes the two branches contradict each other.
- **A derived column whose parent attribute can change needs a propagation
  rule before that attribute becomes editable anywhere.** The first four R0
  columns derive from an immutable link; `ShareToken.owner` derives from
  `Company.owner`, which an operator can edit. A trigger written for the
  immutable case then refuses **every** write to the child, not only a write
  to the owner column: on `UPDATE`, `NEW.owner` carries the value already
  stored while the parent now names a different one, so an ordinary rename
  raises *does not match* and the row is wedged. The trigger holds both values
  already, so it distinguishes them: `NEW` different from `OLD` is a caller
  moving the row, refused unless it equals the parent's current owner;
  `NEW` equal to `OLD` while the parent differs is a **stale** row, re-derived
  rather than refused, so the column converges on the next write.
  Between the parent's change and the child's next write **the policy reads a
  stale owner** — the old owner still sees the rows and the new one does not —
  so an owner-transfer feature carries an `AFTER UPDATE` trigger on the parent
  that re-derives its children. Until one exists, the editable path is closed:
  `Company.owner` is read-only on an existing company in the admin, and
  writable only on the add form.
- **A re-parent is refused when it changes the owner and allowed when it does
  not.** The rule above separates a caller moving the row from a stale row
  whose parent moved, and there is a third case it does not reach: the row is
  given a **different parent**. `NEW.{column} IS NOT DISTINCT FROM
  OLD.{column}` is true there too, so a trigger that only re-derives in that
  case hands the row to whoever owns its new parent, silently — and the first
  R0 shape refused exactly that. It also *allowed* a re-parent within one
  owner, which a blanket link test would take away: a draft offering can be
  pointed at another share class of the same company today, and the admin
  offers it. So the guard is about the owner, not the link:

  ```sql
  IF NEW.{parent_fk} IS DISTINCT FROM OLD.{parent_fk}
     AND parent_owner IS DISTINCT FROM OLD.{column} THEN
      RAISE EXCEPTION '{table} may not move to another owner, % to %',
          OLD.{column}, parent_owner;
  END IF;
  ```

  Four cases, and each has to land somewhere deliberate: link unchanged and the
  parent's attribute moved, **follow**; link changed to a parent with the same
  owner, **allowed** and the column does not move; link changed to a parent
  with a different owner, **refused**; the caller moving the column itself,
  **refused** unless it already equals the parent. `offerings/0006` is the
  reference spelling. `users/0021` writes the guard on the link alone, which is
  equivalent there and only there, because `UserProfile.user` is a
  `OneToOneField` — every re-parent of one of its children necessarily changes
  the owner. If that ever stops being true, this is the sentence that says
  where the two forms part.

  **The four lanes word this refusal four ways, and that is deliberate.** Each
  lane's tests assert its own message, because the assertion is what proves the
  *trigger* refused rather than a unique index standing in for it. Unifying the
  wording would make two lanes' tests pass on each other's refusals, which is
  the check those assertions exist to make. Keep the shape, not the string.

  Nothing on either side of this is visible to the SQLite suite, which is how
  it reached `tokens/0024` and was found by the full PostgreSQL suite three
  lanes later.
- **A replacement condition is read backwards as well as forwards: what did
  the branch it replaces refuse *or allow*, and where does each of those cases
  land now?** The amendment above was red-proved for the two properties it
  added, by its author and by two reviewers, and none of us enumerated what the
  condition it replaced had been covering — so a refusal was dropped and stayed
  dropped across three lanes. The correction to that then dropped a permission
  the same way, in the same afternoon, by asking only what the old branch
  refused: **both halves are the question.** Proving what a change adds says
  nothing about what it removes, and a trigger branch is where that gap is
  least visible, because the cases it stops refusing raise nothing and the
  cases it starts refusing appear in no test that was written for them.
- **The trigger's local variable takes its type from the column it reads**,
  `parent.{column}%TYPE`, rather than naming a type. Four R0 parents are
  `uuid` and the user is a `BigAutoField`, because `CustomUser` extends
  `AbstractBaseUser` rather than `BaseModel` — so a hard-coded `uuid` is right
  four times and wrong the fifth, and `users/0020`'s hard-coded `integer` is
  right until an id passes 2^31 and then raises `integer out of range` inside
  a trigger, on a write that has nothing to do with ids ([#323](
  https://github.com/RonildoBraga/ledova/issues/323)). **Neither spelling is
  safe to copy: the type belongs to the column.**
- Python supplies as well as the database enforcing: a small model mixin fills
  the column in `save()`, because the trigger is PostgreSQL-only and `make test`
  runs on SQLite. `bulk_create` bypasses `save()`, which is how a test reaches
  the trigger at all.
- The **reverse** drops the trigger, relaxes the column, nulls it and removes
  it. The nulling step is redundant — `RemoveField` follows it, and while the
  trigger stands a `SET NULL` is repaired rather than refused — so **there is no
  guard on it**. The evidence that the migration reverses is the round trip with
  real rows, not a test asserting a non-behaviour.
- **Settle deferred constraints before the backfill writes, in both
  directions.** `SET CONSTRAINTS ALL IMMEDIATE` at the top of `backfill` and of
  `unfill`, guarded on `vendor == "postgresql"`. The condition that needs it is
  **a row the migration writes twice**: the second `UPDATE` queues a deferred
  FK-check event whatever columns it touches, because PostgreSQL's
  keys-unchanged skip cannot apply to a row version the current transaction
  produced, and `ALTER TABLE` then refuses with `cannot ALTER TABLE ... because
  it has pending trigger events` while *any* event is pending on the relation,
  not only the constraint being dropped. Two owner columns on one table is the
  common way to reach that, and it is how `tokens/0023` reached it, but a
  single column backfilled in two passes over the same rows reaches it just as
  well; **it is the second write that matters, not the second column**. The
  cause is not the backfill re-arming the new column's own constraint —
  `AddField` emits `SET CONSTRAINTS <that one> IMMEDIATE` inline and it holds.
  Rows written once never see it, which is why `users/0020`, `wallets/0008` and
  `offerings/0005` are clean. Settling *before* the writes rather than after
  also moves a failing backfill's error to the `UPDATE` that caused it.
  **It goes in every R0 migration, including the ones where it is measurably
  inert.** `tokens/0024` writes each row once, so removing the settle leaves
  its populated round trip green — measured, not assumed. It stays anyway,
  because the condition is a property of the *backfill*, not of the schema: a
  later reviewer adding a second pass, or a lane copying this template for a
  table that takes two columns, gets the guard already there rather than
  discovering the failure on a populated database. An inert line inside an
  applied migration cannot be added later — that is #262's ruling — so the
  choice is to carry it from the start or to accept that the next lane pays
  for it. A lane whose settle is inert says so in its body, so nobody reads a
  green round trip as evidence the guard works. **One call before the first
  write in each direction is the whole of it**, and `tokens/0023` carries a
  third in `drop_triggers`: on the reverse path either that call or `unfill`'s
  carries it alone, measured by disabling each in turn, so the pair is
  redundant rather than layered. `tokens/0024` copied all three before dropping
  the extra, which is why the count is written down here rather than left to be
  inferred from the lane a reader happens to open.
- **Audit the app's serializers for `exclude`-style field sets before adding the
  column.** A `ModelSerializer` with `exclude = (...)` turns a new model field
  into a *required writable API field*; two in `users` did exactly that, and
  nothing but the suite says so. An explicit `fields` tuple is unaffected.


**Stage R1 — the mechanism, beside the querysets.** Roles, aliases, the
principal, and a policy on every tenant table, while `visible_to_user` still
runs. Both mechanisms hold at once on purpose:

- **Three roles on one database, and the third is what makes the second
  possible.** `ledova_app` connects for the API: not an owner, no `BYPASSRLS`.
  `ledova_operator` has `BYPASSRLS` and serves the admin, the operator console,
  the workers and the management commands. `ledova_migrate` owns the tables and
  runs the migrations. Folding migration into the operator role would make the
  operator the table owner, and `FORCE ROW LEVEL SECURITY` would then scope the
  one role whose purpose is being unscoped.
- **The principal is set where DRF resolves the user, not in middleware.**
  `HybridJWTAuthentication` runs in `APIView.initial()`, after every Django
  middleware, and a bearer request carries no session — so in middleware
  `request.user` is anonymous for the whole API. `SetsThePrincipalOnTheConnection`
  overrides `initial()` on the four shared bases, and
  `shared/tests/test_principal_coverage.py` fails if a routed view neither
  carries it, runs on the operator connection, nor states a reason.
- **A request with no acting user runs on the operator connection.** The four
  webhooks are that case: an external system tells us about a subject we did not
  authenticate, so there is no principal to set and every tenant read would fail
  closed. They carry `RunsOnTheOperatorConnection`, and the admin is recognised
  from the URLconf's `app_name` rather than from the path, because a path prefix
  grants the privileged connection *before* resolution.
- **`SET` at session level, `CONN_MAX_AGE = 0` on the app alias.**
  `ATOMIC_REQUESTS` is refused by Django with async views — and this codebase has
  three places that deliberately commit and then raise, which `ATOMIC_REQUESTS`
  would silently undo, turning a spent challenge back into a replayable one. With
  no connection reuse there is no stale principal to leak, so the `RESET` in the
  middleware's `finally` is hygiene rather than the load-bearing part.
- **Cancel and modify actions have their own durable identity.** A read-only
  action-context request returns canonical decimal strings for the current
  quantities and price. It allocates no journal or challenge. A deliberate
  action receives a fresh account-scoped UUID; retries keep that UUID, even when
  another deliberate action chooses equal terms. `tokens/0038` records immutable
  order, account, wallet, token, purpose, domain and full replacement values.
  `OrderCancelV1` and `OrderModifyV1` bind those identities in the signature.
- **Provider reads stay outside action transactions.** Registration commits a
  pending intent before issuance preflight. Execution first authenticates and
  checks the pending challenge in a short transaction, then performs any
  advisory balance RPC. The final durable transaction rechecks authorization,
  domain, challenge and current business state, and commits spend, local order
  changes, modification logs and the recorded outcome together. Only the
  existing cancellation/modification business refusals at that final decision
  record a refusal. A provider or unexpected failure before the durable commit
  leaves the action pending and unspent; a lost response after commit recovers
  the recorded outcome. Issuance checks do not record terminal refusals.
  Enclosing transactions and disabled autocommit are refused.
- **Recovery returns history alongside current state.** An authorized terminal
  action is read before checking pending-only credentials or current deployment.
  Recovery uses the owned plain order and can fall back to recorded token display
  metadata; it does not grant access to a now-hidden token. The original result
  remains immutable while the returned order can change. A terminal replay
  performs no second mutation or event publication. Events use the existing
  after-commit mechanism; there is no outbox or exactly-once delivery guarantee.
  The new journal participates in account RLS, and PostgreSQL guards protect its
  identity, challenge linkage and terminal outcome. Actual API, scoped-role and
  same-action process controls cover the boundaries.
- **Issued trading intent is immutable.** `tokens/0035` adds database bounds for
  order/swap amounts and their existing status/type values. Partial settlement
  may still leave an OPEN order with nonzero fills, and a minimum fill may exceed
  its remaining quantity. A PostgreSQL trigger freezes each signing challenge's
  issued envelope and prevents resetting or replacing its first consumption.
  The existing purge of expired, unspent challenges remains allowed.
- **New swaps retain their original settlement context.** Matching captures the
  V1 domain, addresses, exact integer strings, deadline, scales, display and
  order/account/wallet/asset/deployment identities without provider I/O. The full
  EIP-712 digest is separate from the unchanged domain-free `order_hash`.
  `tokens/0039` preserves existing rows as legacy and protects new contexts and
  their identity fields against replacement or deletion on PostgreSQL. Exact
  scoped reads recover the named swap; new signatures and approvals recheck the
  caller's current verified wallet/account/order binding and captured context.
  Either captured party may supply the signature through an authorized
  participant. `tokens/0040` freezes the parent order's account/wallet/address
  identity and prevents replacing either referenced parent. An unchanged V1
  swap can be updated by a currently bound, verified participant without
  reading the other private order. INSERT and legacy derivation retain their
  original checks. Private cross-account matching and outcome writes needing
  both parents remain separate #5 dependencies; `tokens_swaporder` remains
  `AWAITING_RLS`.
  New execution claims record every signed argument, both signatures, original
  domain/digest and contract recipient. Receipt attribution retains that
  identity after configuration changes. Provider admission reuses the existing
  cached chain check; it does not establish a fresh RPC observation at every
  boundary. Legacy signatures are neither reconstructed nor invalidated.
- **One current swap execution is claimed before preparation.** A fresh READY
  row receives a transaction UUID and becomes EXECUTING in a durable transaction
  before balance checks, building, signing or sending. Competing callers cannot
  prepare another attempt. Signature writes also reread the locked swap. Shared
  order locks are acquired by primary key, followed by challenge, swap and
  current transaction locks where needed; matching then selects by the existing
  price/time priority. Receipt I/O runs outside these locks, and each outcome
  rechecks the order links, current UUID, both recorded hashes and fresh terminal
  transaction evidence before changing reservations. A local failure before any
  send can unwind once; a missing receipt, provider exception, monitor timeout,
  elapsed deadline or unattributed nonce use cannot. A process death after the
  claim leaves unresolved history. This does not supply durable signed-byte
  recovery, request idempotency, aggregate reservations, a complete cross-row
  state machine or trading RLS; those remain in #5 and #6.
- **The strict read is deliberate.** Policies call
  `current_setting('app.user_id')::bigint` with no `missing_ok`, so an unset
  connection raises `unrecognized configuration parameter` and a cleared one
  raises `invalid input syntax for type bigint: ""`. Both are loud. The
  alternative fails closed *and silent*, and an empty result set is
  indistinguishable from "you own nothing", which is exactly the ambiguity this
  mechanism exists to remove.
- **Two helpers where one would do, today.** `app_visible_company_ids()` and
  `app_manageable_company_ids()` have identical bodies and are called by `USING`
  and `WITH CHECK` respectively. Five of the seven company-derived tables are
  equal only *transitively* through `Company`, and there is standing pressure to
  widen `Company.visible_to_user`; one helper would destroy the distinction at
  the moment it starts mattering.
- **Neither helper is `SECURITY DEFINER`.** Running as the caller means
  `users_userprofile`'s own policy applies inside the function, so the helper's
  `WHERE` is a second opinion rather than the only guard. The cost is a rule:
  `companies_company`, `users_userprofile` and the membership table carry **leaf
  policies** — direct comparisons against `current_setting`, never a helper call
  — or a policy calls a function that queries the table the policy is on, and
  PostgreSQL's error for that is stack-depth exhaustion.
- **Tenancy predicates are positive.** `owner_id IN (SELECT …)` is NULL for a
  NULL owner and hides the row, which is the fail-closed behaviour a nullable
  owner column relies on; `NOT IN` and `<>` invert under NULL and make a legacy
  row visible to everyone. A test reads `pg_policies` and refuses a negation.
- **Policies are written per command, never one `FOR ALL`** — and the `UPDATE`
  policy's `USING` is the **read** scope, not the write one. PostgreSQL applies
  it to `SELECT … FOR UPDATE`, so a row the read policy admits and the update
  policy does not can be read and never locked, and `select_for_update().get()`
  turns that into `DoesNotExist` rather than a refusal. `USING` governs who may
  lock, `WITH CHECK` governs who may write, so all the narrowing lives in
  `WITH CHECK`; `DELETE`'s `USING` carries the same write scope, and a test reads
  `pg_policies` and requires `UPDATE`'s `WITH CHECK` and `DELETE`'s `USING` to be
  textually equal for **every** policied table, because both install from the
  same term.
- **`INSERT`'s `WITH CHECK` is the one command that may differ, and only where
  the catalogue says so.** `INSERTABLE` names the tables where creating a row
  and writing to an existing one are not the same permission, and the installer
  applies it to `INSERT` alone. There is one today: a new user's first
  `customer_accounts_account` cannot satisfy the member term at insert, because
  `ensure_defaults` creates the row and adds the membership on the next line, so
  the term is false for the statement that creates it and true for every
  statement after. The director is known at insert, so `INSERT` admits it —
  *you may create an account you direct, and write to accounts you are a member
  of* — while `UPDATE` and `DELETE` do not, since widening deletion to a
  director is a separate decision nobody has taken (R19). `INSERT_ONLY_REASONS`
  carries that sentence beside the term and a test refuses a reason shorter than
  200 characters. **The read term is not widened either**, so between the insert
  and the membership the director holds a row it can neither see nor delete;
  `ensure_defaults` carries `@atomic()` from `shared.db`, which opens on the
  alias its queries go to and wraps the create and the membership together, so
  there is no state where one exists without the other. R23 is why that
  decorator is enough: a bare `@transaction.atomic` would have opened on
  `default` while the router sent these writes elsewhere.
- `SELECT` carries the read scope and `INSERT`, `UPDATE` and `DELETE` carry the
  write scope, as separate statements. `companies_company` is read at two scopes on purpose —
  `visible_to_user` for issuer surfaces and `all()` for the market — and one
  `FOR ALL` policy under `FORCE` can only encode the stricter of the two.
- **A table reached past a company carries the public-visibility term its own
  querysets already use.** `app_visible_company_ids()` is the set a principal
  *owns*, not the set they may *see*: the directory reads companies through
  `open_to_investors()` and the market reads tokens through
  `deployed_with_contract()`, neither of which was ever owner-scoped. An
  owner-only policy empties the browse surface every investor starts on and
  turns the subscribe path's `select_for_update().get()` into `DoesNotExist`.
  Eligibility stays in code; **RLS decides visibility, not eligibility**.
- **A visible row's parent is visible.** For every non-nullable foreign key
  between policy tables, a row admitted by the child's `SELECT` policy must have
  its parent admitted by the parent's, or `select_related` deletes the child:
  the join is `INNER`, and Django strips an unused `select_related` join for
  `count()`, so **the count disagrees with the page**. Measured on the market
  before it was fixed — `count 1`, `rows 0`, same transaction. An invariant test
  enumerates the foreign-key graph and asserts closure per principal, rather
  than the rule being remembered per view.
- **Rows the platform owns are readable by every principal.** A wallet named as
  a company's `operator_wallet` is not a tenant's row; hiding it from someone
  who may see the company is the same defect one column along, and the account
  that holds such a wallet follows immediately, because a wallet's
  `user_account` is not nullable. Writes on those rows stay on the operator
  connection. The wrong fix is to narrow the company's public term to companies
  whose operator wallet happens to be visible — that makes a company's public
  visibility depend on a wallet's ownership, which nobody would find by reading.
- **Every table is classified, and the classification is enumerated rather than
  described.** `shared/db/policies.py` is the catalogue: a policy, a stated
  reason for carrying none, or a named R0 column it is still waiting for. The
  test compares it against `django.apps` in both directions, so a new model with
  no entry fails and an entry naming a dropped table fails.
- **The migration reads the catalogue rather than carrying frozen SQL, so a
  change to the catalogue needs its own migration.** `shared/0004` imports
  `HELPERS` and `POLICIES` from `shared/db/policies.py`, which is why a fresh
  database always gets whatever the module says today and re-running the
  installer there is a no-op. The consequence is the part to remember: every
  change to `policies.py` silently changes what `0004` installs on a **fresh**
  database while every **existing** database keeps what it was given, so each
  such change needs a migration re-running the installer or the two diverge.
  `shared/0005` is the first instance, and its reverse is `noop` rather than
  `remove` — it replaced policies rather than installing them, and a
  replacement that cannot be undone should say so rather than do forward work
  under a reverse. Reversing it with `remove` took a database from 80 policies,
  20 forced tables and 4 helpers to none of each, while `django_migrations`
  still said `0004` was applied.
- **`check_rls_catalogue` is what makes that rule enforceable rather than
  remembered.** It was the only rule here without a script, and it is the one
  that is invisible when broken: both databases work, they are simply
  different, and the difference surfaces weeks later as a defect on one
  deployment and not another — #355 is the shape. The command reads what is
  installed, then runs `policy_sql.install` itself inside a transaction it
  rolls back and reads the result of that, and compares the two. Three things
  about it are deliberate:
  - **It compares `pg_get_expr` output against `pg_get_expr` output, never
    against the text in `policies.py`.** PostgreSQL rewrites an expression when
    it stores it — parenthesising, qualifying, making casts explicit, turning
    an `IN` into `= ANY (ARRAY[...])` — so the catalogue string resembles
    neither side. A gate comparing raw text would report formatting as drift,
    get pinned, and then be ignored.
  - **It runs the installer rather than reimplementing it.** Which expression
    reaches which command is `policy_sql`'s business — `INSERTABLE` on `INSERT`
    alone, `readable` on `SELECT` and the `USING` half of `UPDATE`. A gate that
    restated that mapping would be a second source of truth for exactly the
    thing it exists to keep singular. Before rendering, the probe drops every
    policy on the catalogued tables inside its rollback transaction. Extra
    permissive grants therefore cannot survive into the expected policy set.
    It compares policy roles and permissiveness as well as command and clauses.
    Helper comparison includes the zero-argument function's body, language,
    volatility, security mode, strictness, parallel and leakproof flags,
    configuration and return type.
  - **The probe rolls back, and a test asserts the installed policies are
    unchanged afterwards.** It takes the locks the migration takes, briefly, so
    it belongs after `migrate` on the PostgreSQL job beside `check_rls_roles`,
    and it is also the command an operator runs against an installation to ask
    whether it is the one the code describes.

  A catalogue that will not install is reported as a finding rather than
  raised, because a fresh database could not be built from it either.
  Run this privileged command after migration when validating a deployment.
  The app does not maintain a separate startup hash or run a DDL probe on its
  scoped connection.

  Capital-increase and issuance requests have company policies installed by
  `shared/0007`. A subscriber can also read the issuance request linked to their
  subscription, so withdrawal still reports a claimed issuance as a business
  refusal; only the issuer can change or delete the request. Their R0 columns
  already exist when `shared/0004` first reads
  the catalogue on a fresh database. `AWAITING_R0` entries explicitly name their
  missing columns, and the command fails when one is already `NOT NULL` in the
  migrated schema. Swap wallet columns are also complete; `AWAITING_RLS` records
  their remaining trading-policy work instead of claiming that R0 is unfinished.

**How R1 is proven, and where the proof deliberately diverges from
production.** Three aliases are three *connections*, and Django's `TestCase`
opens a separate transaction per connection — so fixtures written on one alias
are invisible on another for the whole test. Converting the suite to
`TransactionTestCase` to work around that would mean truncating tables for 246
test classes. So the proof is split, and each part proves something the others
cannot:

- The **tenancy proof** takes the app role on the test connection with `SET ROLE`
  and sets the principal there. `SET ROLE` changes `current_user`, superuser-ness
  is not inherited through it, and `FORCE ROW LEVEL SECURITY` binds the owner
  too — so the policies evaluate exactly the predicates the production role
  meets, while the fixtures stay visible because it is one connection. In
  production the app connection logs in as the app role and never `SET ROLE`s;
  in tests a privileged connection becomes it. **That is the divergence, and it
  is bounded to which role the connection arrived as.**
- The **role plumbing** is asserted by `manage.py check_rls_roles`, not by a
  test, because it is the half no test can see: the app role lacks `BYPASSRLS`
  and owns no table, the operator role has it, the migrate role owns the tables,
  and a fresh connection carries no principal. It runs in CI and at startup.
- The **router and the principal** have unit tests of their own, since neither
  is exercised by the two above.

**Stage R2 — the conversions, and the failure direction they inherit.** A task
converted to run scoped takes its principal as a **required argument with no
default**, because the principal belongs to the *enqueue* rather than to the
task: a task with three enqueue sites has three answers, and one omissible
argument would let a caller silently downgrade to the operator connection. A
required one turns that into an error at author time — the first conversion
found seven existing callers that way.

The failure direction is worth stating because it is **invisible from the task's
own code**. The worker process sets its ambient alias to the operator one, so a
task that forgets to select a principal at all runs **unscoped**, not empty.
That is the right direction for a sweep, which needs to see every tenant, and
the wrong one for a task acting for a user, which would then read rows its
principal may not. Nothing in the task says which it is; only the catalogue
does.

**Why R1 and R2 are separate releases.** With policies on and querysets still
in, a green matrix says the policy is *sufficient*. With the querysets removed,
a green matrix says they were not doing anything the policy misses. Both
directions are needed and only this ordering gives you both — the interval of
double enforcement is not a cost to be minimised, it is the only window in which
the migration is checkable.



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
  which shape a deployment is. Single issuer disables the supporting-payslip
  store, including API and admin reads, uploads and extraction. Claims still
  use their existing classification evidence upload and human review.

## Uploaded files

Every uploaded file is private. There is no such thing as a public upload in
this codebase, and `MEDIA_ROOT` holds nothing an authenticated route serves.

Supporting payslips belong to an existing `InvestorClassification` claim through
`Document.classification`. An uploader may attach an available payslip once,
only to a claim they can access while it remains submitted. Attachment neither
changes the claim's category nor reviews it; extracted figures are not inputs
to eligibility. Permitted operations staff follow links from the claim to its
supporting documents and extraction history and use the existing human review
actions. Migration `documents/0003` seeds a read-only Document operations group
without assigning members or granting classification decisions. Company owners
and company-role accounts cannot use this cross-customer evidence access.

Document and extraction admin pages, changelists and file downloads record
`DocumentRead` rows with reader ID, document and claim UUIDs, kind and timestamp.
The audit contains no extracted values or filenames. A failed audit write stops
the response. Read records survive content purge and have no admin mutation
path. The owner API remains scoped to the uploader; staff use the separately
permissioned admin connection for review. Single issuer has neither surface,
and the operator form refuses conversion while unpurged payslips remain.

- A `FileField` that holds an upload carries `storage=private_storage`
  (`backend/shared/storage.py`) and `max_length=255`, because a private key is
  a uuid path rather than a filename. `PrivateMediaStorage.base_url` is `None`,
  so reading `.url` raises rather than quietly returning a `/media/` path that
  `django.conf.urls.static` would serve to anyone while `DEBUG` is true. The
  three today are `companies.CompanyDocument.file`,
  `documents.Document.file` and `users.InvestorClassification.evidence_file`.
  Lifecycle discovery follows this storage declaration and the private alias,
  so S3 and GCS fields receive the same deletion hooks and reference protection
  as local files. It must not depend on filesystem storage inheritance.
- The upload path names nothing about the uploader. `company_document_path`,
  `document_upload_path` and `investor_evidence_path` all build
  `<owner uuid>/.../<random uuid><ext>`: a leaked key says which row it belongs
  to and nothing else. Never put a primary key, an email address or the
  caller's original filename in a stored key — the original filename lives in
  a column and is handed back in `Content-Disposition` by
  `stream_stored_file(field, mime_type, filename)`.
- **A file is owned by its row, and a file with no row is deleted.** Django has
  not removed a file on row delete since 1.3, so nothing did: an ordinary
  `DELETE` answering 204 left the bytes behind, and retention here is
  row-driven — `purge_expired_evidence` enumerates rows and deletes their
  files, so a file with no row was unreachable by every mechanism meant to
  remove it. Two things now hold the rule, because neither is enough alone.
  `shared.apps.SharedConfig.ready` connects a `post_delete` receiver for every
  private `FileField` it discovers, and that receiver deletes **through
  `transaction.on_commit`** — deleting inside the transaction would mean a
  rolled-back delete restores the row and loses the file, which is worse than
  the bug it fixes. And `shared.services.orphaned_files` sweeps what no
  receiver can reach: a process killed between the file write and the commit
  runs no compensating code. It deletes only files no row references that have
  not changed for `GRACE` (24 hours), walks only `SWEPT_STORAGE_PREFIXES`, and
  runs nightly as `sweep_private_uploads` or by hand as
  `manage.py sweep_orphaned_files --dry-run`. **The grace period is what makes
  sweeping the default safe**: a file written moments before its row commits is
  briefly indistinguishable from an orphan — that window is exactly the defect
  #176 fixed — and 24 hours is a margin no commit will ever need.
  Reference: `backend/shared/storage.py`. Gate:
  `backend/shared/tests/test_orphaned_files.py`, which walks
  `apps.get_models()` and fails for any private `FileField` that is neither
  swept nor named in `RETAINED_AFTER_ROW_DELETE` with a reason — so a fourth
  file-holding model cannot be added without deciding which it is. It derives
  each model's storage prefix by calling `generate_filename` on an unsaved
  probe instance, so it checks every declared field rather than only the rows a
  test happened to create.
  `backend/shared/tests/test_cloud_storage_lifecycle.py` exercises the S3 and
  GCS adapters with synthetic objects: startup registration, live references,
  committed and rolled-back deletion, rollback uploads, grace and retained
  evidence. These checks require no filesystem path or live bucket.
- **Classification evidence and attached supporting payslips use retained
  storage.** Classification evidence has a retention horizon
  and outlives its subject on purpose; account deletion does not purge it
  early. `purge_classification_evidence` is the only thing that removes it, and
  `users/` is in `RETAINED_STORAGE_PREFIXES` so the sweep never walks it. The
  consequence is that a **hard delete of a classification row carrying evidence
  is itself the defect** — the surviving file is correct behaviour, and the row
  should refuse or soft-delete instead. Member deletion withdraws a submitted
  classification; the admin cannot hard-delete it and its account is protected.
  `documents.Document` is a conditional entry in `RETAINED_AFTER_ROW_DELETE`:
  unattached files remain under the swept `documents/` prefix, while attachment
  copies the original bytes to `users/supporting-documents/` and removes the
  old copy only after commit. The shared file lifecycle receiver refuses a
  cascade that would delete a linked row still carrying content. The document
  retention service clears the file and every extraction only after the claim
  horizon; failed storage operations leave a retryable reference.
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
  is not the secret here; the bytes are. An admin route that *acts* on a row
  rather than reading its bytes takes the sibling helper described under
  [Admin row actions](#admin-row-actions). **This is an operational change, not
  only a code one**: a staff account that carried nothing but `is_staff` could
  previously open every one of these routes. Before deploying, grant
  `documents.view_document`, `companies.view_companydocument` and
  `users.view_investorclassification` to the operators who need them.
- **Uploads are checked before permanent storage.** All three writable file
  serializers call `shared.uploads.validate_upload`. It reads at most the byte
  limit plus one control byte, requires a clean ClamAV INSTREAM verdict, and
  probes the actual PDF, PNG or JPEG in a resource-limited child process. The
  detected type must match both MIME metadata and extension. The original
  evidence bytes remain unchanged; the stored size and MIME come from the
  checked bytes. Encrypted/repaired PDFs, truncated files, animated images and
  documents over the page, pixel or decoded-byte bounds are refused. A refused
  upload creates no permanent file, row or extraction task. An
  admin file route streams with `Content-Disposition: attachment` so a row that
  predates the allowlist downloads instead of rendering script on the `/admin/`
  origin; the owner-scoped API route stays `inline`, since it only ever hands a
  caller their own bytes.
- `UploadProtectedView` installs a counting upload handler before authentication
  can trigger multipart parsing. The ASGI entrypoint bounds actual request bytes
  and body arrival time before Django spools them; the WSGI entrypoint bounds
  reads and declared size. Each authenticated create attempt and its actual file
  chunks consume shared Redis rolling quotas before scanning or saving. Bytes
  parsed during successful cookie CSRF authentication are charged afterward.
  Requests refused before authentication completes still have ingress limits;
  they have no authenticated user quota. Scanner/cache failures return 503;
  quota denial returns 429 with `Retry-After`. See
  [upload operations and limits](OPERATIONS.md#upload-validation-and-resource-limits).
- Extraction rereads stored files with the same byte cap, rescans them, and
  renders only the first page in the bounded decoder child. Limits apply before
  rasterization; the result is a bounded PNG without the original metadata.
  The child has address-space, CPU, wall-time and output limits. It is not a
  security sandbox: it runs as the backend/worker OS user, so decoder patching
  and deployment isolation still matter. A scan or decoding failure leaves the
  retained original intact and marks extraction failed; an operator can rerun it
  after fixing the dependency. These checks do not retroactively certify files
  already stored or change their authenticated download and retention rules.
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

## Admin row actions

**A custom admin route that acts on a row is registered with
`shared.utils.admin_actions.admin_action_path` (or `admin_action_re_path`),
never with a bare `self.admin_site.admin_view(...)`.** The reasoning is the one
`admin_file_path` is built on, applied to writes: `admin_view` checks only that
the caller is active and staff, which is weaker than the change page beside it.
Fifteen wrappers guarding twenty-three URL patterns admitted any `is_staff`
account to deploying, pausing and unpausing a share token, executing or
rejecting a mint, updating a NAV, every company and offering transition, the
subscription actions, executing a share issuance or capital increase, and
adding or removing a whitelist entry on chain. Those are chain-side and
compliance operations, and each of them was refused the change page for the
same row.

The helper **owns the row lookup**, which is what makes the guarantee
structural rather than remembered: it checks `has_change_permission(request)`,
resolves the row through `model_admin.get_queryset(request)` — the same rows
the change page resolves, so an admin that narrows its queryset narrows its
actions with it — checks `has_change_permission(request, instance)`, and only
then calls the view with the instance rather than the uuid. A view therefore
*loses* its `get_object_or_404` line when it converts; it cannot forget the
check without abandoning the helper and taking a gate failure. Pass `queryset`
only to widen the fetch, as `SubscriptionAdmin` does with
`Subscription.objects.with_relations()`. It is a **callable taking the
request**, named `rows` rather than `queryset` for a reason: written as
`rows or model_admin.get_queryset`, a caller who passed a queryset instead of a
callable would have had an *empty* one silently replaced by the unrestricted
default, so the narrowing would vanish exactly when it mattered. It is
`rows is None` instead, and a non-callable now fails loudly.

The helper takes the row's uuid from a capture named `uuid`, which every route
uses today. A future route capturing `pk` or `object_id` fails with a
`TypeError` rather than a clear message; that is a constraint the helper imposes
rather than a rule the product needs.

It answers **403, not 404**, for the reason given for the streaming routes
above: the caller is a named staff member who reached the route from the admin,
and the sibling change page already answers 403 for the same row.

`has_change_permission` is the check for all of them, because every one of these
routes mutates the row or acts on chain on its behalf; a route that only reads
is a file route and belongs to `admin_file_path`. The two mint routes insert a
`MintRequest` rather than change the row they hang off, and they still check
`change` on that row rather than `add_mintrequest`, because
`MintRequestAdmin.has_add_permission` returns `False` unconditionally — gating
them on `add` would gate a working operator action behind a permission the
product never grants to anyone, superuser included. Reference:
`backend/shared/utils/admin_actions.py`. Gate: the `bare-admin-view` rule in
`scripts/check-layers.py`, whose `RULE_HELPERS` excludes `shared/utils/` by name — the
helper a rule points at is not subject to it, and saying so beats relying on
`layer_of` returning `None` for a directory that happens not to be named after
a layer. Test:
`backend/shared/tests/test_admin_row_actions.py`, which derives the route list
from the resolved URLconf rather than naming routes, so a new row action is
covered the day it is registered.

**The same principle governs fields, not only actions: the admin may not be more
permissive than the API for the same row.** `CompanyUpdateSerializer` refuses to
change `acn`, `abn` or `company_type` once a company leaves `DRAFT`, and never
exposes `owner` at all — and `CompanyAdmin` let staff change all four at any
status, so the rule the API stated was defeated by opening the change page.
`CompanyAdmin.get_readonly_fields` now locks them, in the shape
`ShareTokenAdmin.get_readonly_fields` already used for a deployed token.

`owner` locks on every existing company rather than only after `DRAFT`, and for a
stronger reason than the serializer's silence: ownership is the tenancy root.
`Company.visible_to_user` and `manageable_by_user` are both `filter(owner=user)`,
so reassigning it moves every company-scoped row to a different tenant with no
record beyond a generic admin history entry. It stays editable on the *add* form,
because the column is `NOT NULL` and locking it there would make an
admin-created company impossible. If an operator ever does need to reassign one,
that is a row action carrying a reason, not an editable field.

Gate: `backend/companies/tests/test_admin_matches_the_api.py`. Neither side is
written out. The immutable set is found by offering the serializer a changed
value for every field it exposes, twice — once with the instance at `DRAFT` and
once past it — and taking the difference, so a field refused because the *value*
is invalid is not mistaken for a field refused because it is immutable. That
subtraction is the whole trick: without it an empty `abn` reads as locked. The
admin side is `get_form(request, obj).fields`. A test asserts the probe finds
exactly `company_type`, `acn` and `abn`, so the comparison cannot pass by finding
nothing. The sweep across every other admin and serializer pair is not written
yet.

**Operationally**: grant `change_` on the eleven models these routes act on —
`assets.asset`, `companies.company`, `offerings.offering`,
`offerings.subscription`, `tokens.mintrequest`, `tokens.yieldtoken`,
`tokens.sharetoken`, `tokens.shareissuancerequest`,
`tokens.capitalincreaserequest`, `users.investorclassification`,
`whitelist.whitelistentry` — to the operators who need them. An operator who
previously worked through these buttons on `is_staff` alone stops being able to,
which is the point.

## Company identifiers

An ACN and an ABN are checked for their **check digits**, not only their length,
and the check runs on every write path. `companies/validators.py` holds both
algorithms; the fields carry them as `validators=[...]`, which is what reaches
the admin (a `ModelForm` calls `full_clean`), and the serializers call the same
functions so the API answers 400 rather than 500. **The residual gap is a direct
ORM write**: `Company.objects.create(acn=...)` runs no validator, and no
`CheckConstraint` can express a checksum. That is stated rather than implied
covered.

`Company.clean()` carries the one rule that needs both fields: **an Australian
company's ABN is its ACN with two check digits in front**, so the last nine
digits of the ABN must be the ACN. That holds for ASIC-registered companies,
which is every `company_type` this product has — it is *not* true of ABNs in
general, and the ABR's own published example, `83 914 571 673`, is the proof:
its last nine digits are not a valid ACN. A test pins that, so the next reader
does not widen the rule to all ABNs.

**What the checks are worth, stated as a number rather than as a feeling.** The
ABN check is a modulus of 89, which is prime and larger than any weight, so it
catches **every** single-digit error. The ACN check is a weighted modulus of 10,
and five of its eight weights share a factor with 10 — so it does not.
Corrupting one digit of ASIC's published example gives 81 candidates and the
check accepts 8 of them, every one at a position weighted 8, 6, 5, 4 or 2.
`test_the_acn_check_misses_only_what_a_modulus_of_ten_cannot_see` asserts that
shape rather than a count, and asserts the set is non-empty so the limitation
cannot quietly disappear. **A checksum is a typo filter, not verification**: only
a registry lookup says a number belongs to a real company, and that is tracked
as its own issue rather than implied by this one.

Reference: `backend/companies/validators.py`. Gate:
`backend/companies/tests/test_identifier_checksums.py`, whose fixtures are the
**published worked examples** — ASIC's `004 085 616` and the ABR's
`83 914 571 673` — rather than numbers this codebase generated. A checksum test
whose expected values came out of the implementation under test agrees with
itself for any algorithm, including a wrong one.

## Wallet ownership and signing

**`VERIFIED` means someone held the private key, not that a hardware device
held it.** The server issues a plain-text challenge naming the address, a
timestamp and a nonce, stores it on the row with its issue time, and on
submission recovers the signer and compares it to the stored address. Three
things bound that, all in `complete_wallet_verification`: the row is locked for
the read-modify-write, the challenge is refused outside
`WALLET_VERIFICATION_CHALLENGE_MINUTES` of its issue time, and it is cleared on
success so a signature cannot be replayed. The identity check itself is
`encode_defunct` plus `recover_message` plus a lowercase compare, standard
EIP-191. Master fingerprint, derivation path and xpub are columns on the model
and appear nowhere in that path, so a signature from a Keystone and a signature
from a script are indistinguishable to it — they are the same ECDSA output over
the same bytes. `signing_preference` is self-declared and client-writable, its
own help text says it does not attest custody, and no backend authorisation
decision reads it. Anything downstream treating `VERIFIED` as evidence of
hardware custody is reading a guarantee the code does not make.

**Two client signing paths therefore exist, and both are legitimate.** The
Keystone path wraps the challenge as a UR/CBOR `eth-sign-request`, renders it
as a QR, and reads an `eth-signature` UR back through the camera; it is what an
air-gapped device requires. The seed-phrase path derives the key in the browser
with `localSigner`, which zero-fills every intermediate buffer in a `finally`
block, signs, and discards the phrase — it is never stored, never transmitted,
and never leaves the tab. The mobile client has always done the second of these
against the same endpoint; the dashboard did not, which made a typed address
permanently unverifiable there and is why the Verify button previously refused
before making any request.

**The seed-phrase path proves ownership locally before it spends anything.**
`deriveAddress` is run first and the result compared case-insensitively against
the wallet's address, so a wrong phrase is refused in the browser with the
derivation path named, rather than by the server after a round trip. The
default path is `m/44'/60'/0'/0/0`; a wallet carrying its own `derivation_path`
uses that instead. The option is offered only on EVM chains, because the
dashboard bundle has no Bitcoin software signer.

**What no automated test can cover is the device round trip.** Nothing in CI
scans a QR code, so the encoder, the animated fragmenting, the camera decoder
and the firmware's own behaviour are exercised only by a human with the
hardware. That is a pre-release check rather than a gate, and it is listed as
one in `docs/OPERATIONS.md`.

Reference: `backend/wallets/services/verification.py`,
`backend/wallets/services/wallets.py`,
`dashboard/src/pages/wallets/hooks/useWalletVerification.ts`,
`dashboard/src/utils/softwareWallet/localSigner.ts`. Gate:
`backend/wallets/tests/test_wallet_verification.py` and
`dashboard/src/pages/wallets/hooks/useWalletVerification.test.tsx`, whose
signature assertion recovers the signer with `ethers.verifyMessage` rather than
re-deriving it through the code that produced the signature.
