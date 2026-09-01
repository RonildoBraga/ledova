# ADR 0002 — PostgreSQL RLS proof; activation deferred

Status: Proposed — mechanism validated; activation is not accepted or shipped
Date: 2026-09-01

## Decision

Keep an isolated PostgreSQL test and SQL helper as evidence that row-level
security (RLS) can enforce tenant filtering. This PR does not create a runtime
role, grants, policies, middleware, session setting, or application connection
switch. Importing the helper has no database effect.

## What the proof establishes

The test creates a unique temporary role with `NOLOGIN`, `NOSUPERUSER`, and
`NOBYPASSRLS`, grants it only the permissions under test, and installs temporary
policies on the exact `wallets` and `portfolios` tables. It proves that:

- unset and empty tenant settings fail closed;
- unscoped reads return only the selected tenant, including multiple account
  identifiers;
- a cross-tenant update is rejected with PostgreSQL SQLSTATE `42501`; and
- the role, grants, policies, and session state are removed after the test.

The database owner can still see all rows, confirming the test exercises the
role boundary rather than an application filter.

The custom tenant setting is caller-settable. This proof protects against an
accidentally unscoped ORM query; it does not protect a compromised database
session or SQL injection that deliberately forges tenant context.

## Why activation is deferred

Table owners and superusers bypass RLS. A production rollout therefore needs a
reviewed owner/application role split and a proven way to set tenant context
after authentication without leaking session state through ASGI connection
reuse. Admin, background-worker, migration, and streaming paths also need
explicit designs. Those properties are not established by this proof.

Coverage is also incomplete. `wallets` and `portfolios` have direct account
keys; indirect tables such as `holdings`, `transactions`, `holding_snapshots`,
`fiat_transactions`, `asset_allocations`, `portfolio_snapshots`, and
`tokens_transferorder` need a separate schema and policy design. The identity
table `customer_accounts_account` needs a bootstrap strategy before it can be
considered for RLS.

## Activation gate

Runtime activation requires a separate ADR and PR covering the production role
model, transaction or connection-scoping discipline, admin/staff/background and
streaming behavior, all tenant-bearing tables, and end-to-end two-tenant
regression tests. Until that work is explicitly accepted, this proof changes no
runtime database behavior.
