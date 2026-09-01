# ADR 0002 — PostgreSQL Row-Level Security as the tenant-isolation backstop

Status: Accepted (design validated; rollout staged)
Date: 2026-09-01
Context: deferred-hardening #1 (tenant isolation). Complements the app-layer
fixes in PR #14; this ADR defines the database-enforced layer beneath them.

## Decision

Adopt PostgreSQL Row-Level Security (RLS) as the enforcement layer for tenant
isolation, so that a forgotten `get_queryset()` scope in the application can no
longer leak another tenant's rows. django-guardian remains for now as the
app-layer read filter and for any genuine object-sharing; RLS sits underneath
as defence-in-depth. The long-term target is to replace guardian's read path
with direct `account_id` filtering (fast, no generic-FK joins), at which point
RLS policies key on that same column.

## Validated mechanism (proven against the dev database)

Policy shape, identical on every tenant table:

```sql
ALTER TABLE <table> ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON <table>
  USING      (<owner_account_col> = ANY (string_to_array(current_setting('app.account_ids', true), ',')::uuid[]))
  WITH CHECK (<owner_account_col> = ANY (string_to_array(current_setting('app.account_ids', true), ',')::uuid[]));
```

Verified behaviour as a non-superuser role:
- session var unset  -> 0 rows (fail closed)
- `SET app.account_ids = '<tenant-B accounts>'` -> only tenant B's rows
- INSERT of a tenant-A row while scoped to B -> rejected by WITH CHECK

## Two hard constraints discovered

1. **Superusers and table owners bypass RLS unconditionally.** The default
   `POSTGRES_USER` (`ledova`) is a superuser, so the app MUST connect as a
   dedicated non-superuser, non-owner role (`app_user`) for policies to apply.
   Correct role split (matches docker-compose service topology):
   - `web` (backend/uvicorn) -> connects as `app_user` (RLS enforced)
   - `migrate` + `worker`     -> connect as owner `ledova` (RLS bypassed;
     correct for migrations and system/background jobs that span tenants)

2. **The session variable must be set AFTER DRF authentication, not in Django
   middleware.** `request.user` is only the JWT user once DRF's
   `HybridJWTAuthentication` has run inside the view; Django middleware sees
   AnonymousUser. A middleware that sets the GUC from `request.user` would
   fail-close every authenticated request.

## GUC-injection design (session-level SET, no request-wide transaction)

`SET LOCAL` needs a surrounding transaction, which is incompatible with the
SSE streaming endpoint and would force `ATOMIC_REQUESTS`. Use session-level
`SET` instead, made leak-safe by always clearing at request start:

- Early middleware: `SET app.account_ids = ''` at the very start of every
  request — overwrites any stale value left on the pooled connection
  (fail-closed default). Runs before any tenant query.
- After authentication (shared authenticated base viewset `initial()`, i.e.
  after `perform_authentication`): `SET app.account_ids = '<user's account
  uuids>'`. Tenant queries run in the view, after this point.
- Connections are reused per worker thread and requests are serialized on a
  connection, so "clear-then-set every request" leaves no leak window.

### Staff / admin
Django admin and staff tooling need cross-tenant visibility. Options, to
decide at activation time: (a) run admin as the owner/bypass role on a
separate route/process; or (b) a policy clause allowing a `staff` GUC set only
for `is_staff` users. (a) is cleaner and keeps the bypass out of band.

## Owner column per table
- Direct `user_account_id` already present: `wallets_wallet`,
  `portfolios_portfolio`. (Phase 1 targets these — no schema change.)
- Needs a denormalised `account_id` (add + backfill + set on write):
  `tokens_transferorder` (keyed only by wallet_address string),
  `wallets_holding`, `wallets_transaction`, `wallets_holdingsnapshot`,
  `portfolios_assetallocation`, and the company/token registry tables.
- Identity/bootstrap tables (`users_useraccount`, the M2M, `users_userprofile`,
  auth user) are intentionally NOT under RLS: the middleware must read them to
  resolve `app.account_ids` before the GUC is set. They remain app-layer
  scoped; a SECURITY DEFINER resolver could bring them under RLS later.

## Rollout (staged, each stage tested + reviewed)
1. **Foundation (safe, inert):** `app_user` role + grants; policies on
   `wallets_wallet` + `portfolios_portfolio`; policy_sql helper; DB-enforcement
   test via `SET ROLE app_user`. Inert while the app still connects as owner.
2. **Activation:** GUC-injection (clear middleware + base-viewset set); switch
   the `web` service to `app_user`; resolve staff/admin bypass; end-to-end test
   proving raw `Wallet.objects.all()` returns only the caller's rows.
3. **Denormalise + expand:** add `account_id` to order/holding/transaction/etc.,
   set on write, add policies — one table at a time using the helper.
4. **Guardian retirement (optional, perf-driven):** replace `get_objects_for_user`
   read paths with direct `account_id` filtering once every table has the column.

## Consequences
- Strong: a forgotten app-layer scope can no longer leak data; enforcement is
  at the database and cannot be bypassed by an ORM mistake.
- Cost: a role split (web vs worker/migrate), a per-request GUC discipline,
  account_id denormalisation across ~13 tables, and RLS-aware tests.
- Trading stays feature-flag-disabled as containment until activation is
  complete and independently reviewed (per #1).
