# Project handover

Last verified: 2026-09-05

## Project context

Ledova is the sanitized public continuation of the private Blueberry codebase.
Preserve existing architecture and behaviour where practical; this transition
is not a clean-sheet rewrite. Never transfer secrets, production configuration,
private operations, private evidence, or private data into this repository.
Address publication blockers here and leave broader production hardening in the
tracked backlog unless a task explicitly changes that scope.

## Current checkpoint

Branch `claude/backend-simplification` (on top of `main` `d6c09ee`) is the
backend simplification pass. The dashboard, mobile app and shared packages were
frozen for the whole pass: every URL, response key, cookie and header they read
is unchanged, and `backend/shared/tests/test_cross_tenant_routes.py` pins the
scoped routes, the operator-only routes and the collection routes per actor.

What the branch did, in order:

- Verified defects closed with regression tests; the company application
  lifecycle fixed and given its first tests.
- Dead code out: unused modules, exception classes, queryset/manager methods,
  service methods, serializers, dependencies; every Django signal replaced by an
  explicit call in the service that creates the row; the `tenancy` app
  dissolved into per-app tests. Lint (`black`, `isort`, `flake8`) is a CI gate.
- Tenant isolation: fail-closed `visible_to_user` / `manageable_by_user`
  querysets on every customer-facing model, owner FKs NOT NULL, explicit
  `company` on token creation, one route matrix. PostgreSQL RLS is not planned.
- Authentication: one auth path, the legacy `AuthViewSet` hardened in place.
  Sessions are simplejwt refresh tokens with the `token_blacklist` app
  (`authentication/services/tokens.py`: refresh rotates and blacklists the
  presented token, signout revokes one session, `signout-all` revokes every
  session, the access token is bound to its refresh via `rjti`). The OTP is
  hashed, expiring (10 minutes) and attempt-capped (5); sign-in, sign-up and
  verification are throttled per address; the DEBUG `000000` bypass is gone;
  cookie flags come from `settings.AUTH_COOKIE`; both tokens live 7 days.
- Per-app simplification with every feature kept: compliance (shared admin
  helpers, seed modules, flat services), users (lifecycle service, one
  preferences guard), tokens (deployment and mint services, one review
  workflow, thin views, market-summary annotations), companies and whitelist
  (table-driven admin transitions, whitelist transaction helper), wallets,
  portfolios and assets (annotated balances, flat sync, thin admins), shared
  and core (no `LoggingContext`, library country lookup, no KYC config layer).
- Docs: `backend/docs/CONVENTIONS.md` is the layering and style reference;
  restating comments, docstrings and section banners removed.

Branch `claude/client-batch` (on top of `main` `1ecb687`) starts the client
work: cookie-sourced POST/PUT/PATCH/DELETE now require the CSRF token
(`HybridJWTAuthentication.enforce_csrf`; Bearer requests are exempt, and the
Authorization header wins over the `access` cookie that React Native's cookie
jar replays beside it), the
`csrftoken` cookie is issued by `auth/verify`, sign-in and email verification
with the auth cookies' domain and secure flag, and the dashboard's axios client
sends `X-CSRFToken` and replays a request once after a `CSRF Failed` 403.
The trading event stream no longer reads a JWT from the `?auth=` query string:
the dashboard authenticates with the `access` cookie and mobile sends the
`Authorization: Bearer` header through `react-native-sse`'s `headers` option
(ISSUES.md item 3).
The shared TypeScript types now mirror the simplified serializers
(`UserProfile`, `AccountExportData`, `Portfolio`, `AuthVerificationResponse`),
`getWalletHoldings` sends no query parameters (the backend ignored them since
PR #68), and the mobile review screen reads the Terms and Privacy links from
`config/publicLinks.ts`, so the localhost `EXTERNAL_URLS` constant is gone.
Shared-package exports no app imports (16 service functions, the unused
types, constants and helpers) and the never-imported dashboard files
(`company/tokens/[uuid].tsx`, `AllocationPieChart`, `TimeRangeSelector`,
`useTransparency`, the `company/hooks` and mobile `components` barrels) are
deleted; the three `/company/*` redirect routes stay for old bookmarks.

Branch `claude/b5-auth-backend` is the auth backend bundle, backward compatible
with the client builds as they are: the token transport is negotiated with the
`X-Auth-Transport: bearer` request header (sign-in, email verification and
`token/refresh` answer in the body only, set no cookie and never read the
refresh cookie; without the header the cookies are set and no body carries a
token), `resend-verification` is `AllowAny` and takes `{ email }`
in the body (an authenticated caller without one is still served by its own
address; the reply is a generic 200), `change-password` revokes every other
session (`TokenService.revoke_all(user, keep_jti=...)`), and the admin change
form lets staff change a user's email with the API's canonical validation
(a colliding address is a form error, not a constraint failure) and revokes
every session of that user on a change. No self-service email change: both
clients show it read-only by design.

Branch `claude/b9-client-fixes` is the client bundle the backend bundles
prepared for. Mobile sends `X-Auth-Transport: bearer` from `axios.create`, so
the cookie transport now carries no token in any body: sign-in and email
verification answer with the identity keys only and `token/refresh` with
`{ "message": "Session refreshed." }`. Both signup email-confirmation screens
post `{ email }` to `resend-verification`; the swap-approval broadcast sends
`signedTransaction` (pinned by `tokens/tests/test_trading_transfer_broadcast.py`);
the trading page lists verified Ethereum and Base wallets only, the backend
rule; token creation sends the issuing `company`; Base wallets render on the
dashboard wallets page and send picker and in the mobile wallet list, home
card and counts; `getUserVerificationStatus` reads `verificationStatus` /
`reviewResult`. Gone: the dashboard transparency placeholder, the shared
`Country` type, `TRADING_ENDPOINTS.TRANSACTIONS`, the order-modification
match fields, the `SWAP`/`MANUAL` snapshot reasons and `CreatePortfolio`.

Branch `claude/b10-bitcoin-manual-signing` restores the Bitcoin send step both
clients lost: for a Bitcoin wallet the prepare call sends `amountBtc`
(`prepareBitcoinTransfer`, typed by `PrepareBitcoinTransferResponse`) and the
sign step shows what to sign (recipient, amount, fee rate, estimated size,
total), takes the signed raw transaction hex the user produced with their own
tooling (`normalizeBitcoinRawTransactionHex` strips whitespace and an optional
`0x`) and broadcasts it; the success state links to the testnet explorer.
The Keystone QR (dashboard) and software/hardware (mobile) EVM paths are
unchanged, `useTransferFlow` treats Base as EVM (whitelist query, 18
decimals, display name from shared-constants) and the trading broadcast
validator decodes legacy and typed transactions through
`tokens/services/signed_transactions.py` (`Account.decode_transaction` never
existed in eth-account 0.14; `tokens/tests/test_signed_transactions.py` signs
real transactions offline).

Branch `claude/b11-mobile-biometric` removes the password at rest from the
mobile app. Biometric sign-in now unlocks a copy of the rotating refresh token
kept behind a biometric-gated SecureStore entry (`requireAuthentication`,
`WHEN_PASSCODE_SET_THIS_DEVICE_ONLY`, the seed-phrase pattern) and exchanges
it at `token/refresh` for a new session; the password is never stored, and a
sign-out revokes the token so the next sign-in is typed once. Every token
write goes through `mobile/src/services/tokenStorage.ts`, which keeps the
gated copy in step with each rotation (silently on iOS; Android's Keystore
asks for biometrics on every gated write and drops the copy when the prompt is
cancelled or the app is in the background, so the next password sign-in stores
it again). The mobile axios client refreshes once on a 401 (single-flight,
replaying the request) and clears every token when the backend rejects the
refresh. The trading broadcast validator also rejects a transaction signed for
another chain id.

## Next work

1. Product call: should modifying an order re-run matching automatically?
   Creation matches; modification no longer reports a candidate match.
2. Deploy note: `ACCESS_TOKEN_LIFETIME` defaults to 7 days again (604800, the
   same as the refresh token). This is safe because the access token carries
   its refresh jti (`rjti`) and `HybridJWTAuthentication` checks that session
   is live on every request, so signout, signout-all, a password change,
   an admin email change and account deletion revoke it immediately; the
   24-hour value only signed dashboard users out daily. Remove any
   `ACCESS_TOKEN_LIFETIME=86400` override to pick the default up.
3. Deploy note: `companies/0003_delete_review_and_signature_models` (with
   `tokens/0013_remove_transferorder_signature_request` before it) drops the
   three unused tables `ApplicationReview`, `ReviewNote` and
   `SignatureRequest`; both migrations are reversible with `migrate`. The
   dead-models bundle adds `portfolios/0004_delete_assetallocation`,
   `compliance/0005_remove_fiat_transaction_and_high_risk_country`,
   `wallets/0006_delete_fiattransaction_drop_unread_columns` (depends on
   compliance/0005) and `users/0017_delete_waitlist`: they drop the
   `asset_allocations`, `fiat_transactions` and `accounts_waitlist` tables and
   ten columns (nine on `wallets`, `holdings.last_synced_block`); all four are
   reversible with `migrate`. Export any `accounts_waitlist` rows you want to
   keep before applying.
4. Deploy note: notifications are live. Transaction confirmed/failed and the
   KYC review outcome create `Notification` rows and defer the push tasks, so
   the in-app inbox (dashboard bell, mobile inbox) fills from day one. Push
   delivery on the phone additionally needs `extra.eas.projectId` in
   `mobile/app.json` and a dev or production build (Expo Go cannot receive
   remote push on SDK 54); the inbox works without it.
5. Deploy/run note: the compose `migrate` service now runs
   `migrate --noinput && sync_monitoring_rules && sync_procedure_templates
   && asset_sync --seed-only`, so a fresh database gets the compliance
   monitoring rules, the alert procedure templates and the verified
   supported assets (all three commands are idempotent and reconcile the
   tables to the seed modules; `--seed-only` touches no network). `make run`
   users must run the three commands once after `migrate`; without the
   first two no monitoring rule exists and no compliance alert is ever
   raised, and without the seed a token declaring a supported symbol is
   quarantined under a suffixed symbol until an operator verifies it.
   Unknown ERC-20 contracts are quarantined as unverified assets keyed on
   their contract address (ISSUES.md item 9); allowlist one with the asset
   admin's `Mark selected assets as verified` action, and switch a contract
   off by deactivating its chain deployment (transfers for it are then
   skipped and logged, never booked). Identity is `(chain, contract_address)`:
   the same address seen on another chain is another contract and gets its
   own unverified row; an operator adds a second chain's deployment to a
   verified row by hand in the admin. Symbol ownership is case-insensitive
   (`usdc` cannot sit next to `USDC`) and a quarantined row is never priced.
   An unconfigured integration (`KYC_PROVIDER` blank) now answers 503
   `Service not configured` instead of 500.
6. Deploy note: the portfolio value series is computed on read
   (`portfolios/services/value_series.py`, from `HoldingSnapshot` x
   `AssetSnapshot`); `GET /api/portfolios/{uuid}/snapshots/` keeps its path,
   parameters and row shape. `portfolios/0005_delete_portfoliosnapshot` drops
   the `portfolio_snapshots` table (fully regenerable, reversible with
   `migrate`) and the nightly `sync_all_portfolios` periodic job no longer
   exists: delete any queued procrastinate jobs under that name. The hourly
   wallet sync now upserts one `DAILY` `HoldingSnapshot` per holding per day,
   so a wallet with no transactions still gets a daily point; nothing is
   fabricated before a wallet's first holding snapshot.

Decisions deferred during the simplification pass (each is a delete-or-keep
call for the owner; the code is kept and working until decided):

- Client-less API surfaces: removed in the dead-routes bundle. Wallets
  `batch-check-balances` is a LIVE client contract (dashboard AddWalletModal,
  mobile `useFetchBalances`, both through shared-services `fetchBatchBalances`)
  and stays. `/api/waitlist/`, `/api/asset-allocations/` and the fiat-purchase
  rows were removed in the dead-models bundle together with their models; only
  `POST /api/fiat-purchases/transak-widget-url/` remains.
- `NotificationPreferences`: fold into `UserPreferences` with the next
  settings-screen change.
- Bitcoin is kept as watch-only wallets plus manual signed-transaction sends
  on testnet/regtest: the app never builds or signs a Bitcoin transaction; the
  user signs with their own tooling and pastes the raw hex, which the backend
  broadcasts (decided, not deferred).
- Mobile app status and the collapse of the four shared TypeScript packages
  into one; both are client-side work and were out of scope here.

The remaining canonical backlog is [ISSUES.md](ISSUES.md).

## Working rules

- Read [CONTRIBUTING.md](CONTRIBUTING.md) before making changes.
- Use only synthetic data, local development, and supported public testnets.
- Never add secrets, private operational artifacts, personal data, production
  identifiers, or private endpoints to this public handover or repository.
- Keep trading disabled as part of deferred-hardening work.
- Keep this file short and update it when a checkpoint or next task changes.
