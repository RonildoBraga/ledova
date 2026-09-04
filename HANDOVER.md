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
  cookie flags come from `settings.AUTH_COOKIE`; access tokens live 24 hours.
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

## Next work

1. Explicit native body-token endpoints for the mobile app.

Decisions deferred during the simplification pass (each is a delete-or-keep
call for the owner; the code is kept and working until decided):

- Client-less API surfaces: `/api/v1/tokens/orders/`, `yield-tokens/`,
  `tokens/{uuid}/can-receive/`, wallets `batch-check-balances`,
  `sync-holdings`, `{uuid}/transactions`, `{uuid}/balances` (PostgreSQL-only
  `DISTINCT ON`), `/api/holding-snapshots/`, `assets/bulk-update-prices`,
  `/api/countries/`, `/api/waitlist/`, anonymous company listing and `acn/`.
- Models nothing writes or reads: `SignatureRequest`, `AssetAllocation`,
  `FiatTransaction` persistence, the unread `Wallet`/`Holding` columns,
  `NotificationPreferences` (foldable into `UserPreferences`).
- The materialised `PortfolioSnapshot` table versus an on-read value series.
- Bitcoin support end to end (`integrations/blockchain/bitcoin.py`).
- The two-reviewer company approval workflow (`ApplicationReview`,
  `ReviewNote`): finish wiring or delete.
- Push notifications: nothing creates `Notification` rows or defers the send
  tasks; wire one producer or keep the model as an admin-populated inbox.
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
