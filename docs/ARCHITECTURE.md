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
| `scripts/` | `init-local-env.py`, the local environment bootstrapper, and `check-comments.py`, the comment gate |

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
| `operators` | The single `Operator` configuration row and `GET /api/operator/` |
| `authentication` | `CustomUser`, the `AuthViewSet`, JWT sessions, email verification codes |
| `users` | Profiles, accounts, preferences, financial profiles, device tokens, notifications, favourite assets |
| `companies` | `Company`, its application lifecycle, and company `Document` records |
| `tokens` | `ShareToken`, `ShareIssuanceRequest`, `ShareIssuance`, `CapitalIncreaseRequest`, `MintRequest`, `YieldToken`, and the trading models |
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

| Layer | Owns | Never contains |
| --- | --- | --- |
| `models/` | Fields, `TextChoices`, constraints, `__str__`, properties over own fields, single-row transitions (guard, set fields, `save(update_fields=...)`, at most about ten lines, raising the app's `APIException` on a bad state) | Queries on other models, multi-step workflows, external I/O |
| `querysets/` | Every reusable query: `visible_to_user`, `manageable_by_user`, status filters, `select_related` bundles, annotations, aggregates; wired with `objects = XQuerySet.as_manager()` | Saves, side effects, calls into services |
| `services/` | Orchestration across models, external I/O (chain, KYC, email), `transaction.atomic` and `select_for_update`; the one place a multi-model workflow lives; plain functions or a class of staticmethods | HTTP objects, serializers, `Response` |
| `serializers/` | JSON shape and input validation; writable FKs scoped in `get_fields()` with `visible_to_user` | Business rules, locking, queries beyond FK scoping |
| `views/` | Permissions, `get_queryset()` returning `Model.objects.visible_to_user(user)...`, serializer choice, one service call, `Response` | Raw `.objects.filter`, try/except that re-wraps an `APIException`, log lines that restate the request |
| `tasks/` | `@app.task` / `@app.periodic`: load the row by uuid, call one service, return a dict | Orchestration, state machines |
| `admin/` | Registration, list/search/filter, operator actions that call the same model transition or service the API calls | A second implementation of a workflow, HTML badge builders |

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
  exception: `TradingTokenViewSet` (`tokens/views/trading_token.py`) returns
  every deployed share token to any authenticated user. It is the market
  directory and is deliberately not owner-scoped. Whether that posture is right
  is an open Phase 1 decision, not a settled one.
- Owner foreign keys are `NOT NULL`, and writable FKs are scoped in
  `get_fields()`.
- Global operator routes require `IsAdminUser`.
- `backend/shared/tests/test_cross_tenant_routes.py` pins the matrix: `ROUTES`
  for detail routes and actions, `OPERATOR_ROUTES` for the admin-only routes,
  `LIST_ROUTES` for collections. A new detail route or action gets a row there
  or a cross-tenant test in its own app.
- `deployment_mode` on the operator row (`single_issuer` or `registry`) records
  which shape a deployment is; it does not change the isolation rules.

## Coding rules

These are held by review, with two exceptions that fail a build on their own:
the comment rule, through `make check-comments`, and the "one migration per
model change" half of the migrations rule, through CI's `makemigrations --check
--dry-run`. The generated design tokens are gated too, by the `git diff
--exit-code` step, though that rule is stated under [Clients and the shared
package](#clients-and-the-shared-package). For every other rule here, a green
pipeline means nobody checked.

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
  token.
- Constants: `TextChoices` next to the model, numeric thresholds as module
  constants in the app's `constants.py`.
- **No comments and no docstrings in source.** Names and tests carry the
  meaning. There is no "unless it is really needed" clause: wanting to explain a
  line is the signal to rename the thing or add a test, never a licence to
  comment it. `make check-comments` enforces this, and
  [the gate](#the-comment-gate) below is the authority on what it covers. The
  rule covers `backend/`, `dashboard/src`, `mobile/src` and the `mobile/` root
  `.ts`/`.js` config files, `packages/shared`, `packages/scripts`,
  `marketing/src`, `contracts/contracts`, `contracts/scripts` and
  `contracts/test`, each by the extensions the gate lists. The root `scripts/`
  tree is outside them: both files there carry a module docstring. The only comment
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
`contracts/contracts`. `TREES` at the top of the script is the machine-readable
copy of that list — change it and this section together.

Two things sit outside it:

- `dashboard/vite.config.ts` and `contracts/hardhat.config.ts` are one directory
  above a covered tree and keep explanatory comments. Being outside the gate is
  not permission to add more.
- The admin templates under `backend/*/templates/` are not checked. They carry
  no comments today; keep it that way.

A green CI run is evidence for the trees in `TREES` and nothing else.

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
