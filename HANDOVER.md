# Project handover

Last verified: 2026-09-03

## Project context

Ledova is the sanitized public continuation of the private Blueberry codebase.
Preserve existing architecture and behaviour where practical; this transition
is not a clean-sheet rewrite. Never transfer secrets, production configuration,
private operations, private evidence, or private data into this repository.
Address publication blockers here and leave broader production hardening in the
tracked backlog unless a task explicitly changes that scope.

## Current checkpoint

The tenant-isolation audit is complete through PR #37 and
[Issue #1](https://github.com/RonildoBraga/ledova/issues/1) is closed. Guardian
is removed. Tenant isolation is enforced by the `visible_to_user` /
`manageable_by_user` querysets and proven by the route matrix in
`backend/shared/tests/test_cross_tenant_routes.py`; PostgreSQL RLS is not
planned.

[Issue #2](https://github.com/RonildoBraga/ledova/issues/2) changed scope:
the unwired v2 session protocol (PRs #39–#65, last checkpoint `963c686`) is
withdrawn per [ADR 0005](backend/docs/adr/0005-withdraw-v2-session-protocol.md).
The challenge/delivery/admission stream is deleted; the remaining v2 session
modules are removed next, and the legacy `AuthViewSet` is hardened in place.

## Next work

Do not continue v2. Harden the legacy auth path in this order:

1. Remove the remaining v2 session core (AuthSession, RefreshCredential,
   v2_credentials, v2_access_tokens, v2_sessions, v2_access) and their tests.
2. Refresh rotation with simplejwt `token_blacklist` (BLACKLIST_AFTER_ROTATION,
   revoke-all via OutstandingToken), replacing UserToken.
3. Hashed, expiring, attempt-capped OTP with a per-email throttle; no DEBUG bypass.
4. CSRF check for cookie-sourced unsafe requests, pending the dashboard change.
5. Explicit native body-token endpoints for the mobile app.

The remaining canonical backlog is [ISSUES.md](ISSUES.md).

## Working rules

- Read [CONTRIBUTING.md](CONTRIBUTING.md) before making changes.
- Use only synthetic data, local development, and supported public testnets.
- Never add secrets, private operational artifacts, personal data, production
  identifiers, or private endpoints to this public handover or repository.
- Keep trading disabled as part of deferred-hardening work.
- Keep this file short and update it when a checkpoint or next task changes.
