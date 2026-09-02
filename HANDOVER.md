# Project handover

Last verified: 2026-09-02

## Current checkpoint

The tenant-isolation audit is complete through PR #37 and
[Issue #1](https://github.com/RonildoBraga/ledova/issues/1) is closed. Guardian
is removed; PostgreSQL RLS activation remains deferred by
[ADR 0002](backend/docs/adr/0002-rls-tenant-isolation.md).

[Issue #2](https://github.com/RonildoBraga/ledova/issues/2) is implemented
through [PR #48](https://github.com/RonildoBraga/ledova/pull/48). PRs #39–#42
added fail-closed verification, the protocol ADR, and legacy/client
characterization. PRs #43–#45 added the session and refresh-history core. PRs
#46–#48 defined and implemented strict v2 access JWT issuance, verification,
and read-only binding to active users and sessions.

Main is `dca41907a4ea0834f933c50c427e178f5136c436`. The 297-test backend suite,
PostgreSQL checks, repository checks, independent reviews, and
[post-merge CI](https://github.com/RonildoBraga/ledova/actions/runs/33582661963)
passed. No v2 endpoint, request authenticator, CSRF boundary, client cutover,
or legacy retirement is wired yet.

## Next work

Continue [ADR 0003](backend/docs/adr/0003-authentication-session-protocol.md)
by first freezing the exact locked-challenge credential, delivery-state,
rate-limit, and key-rotation profile. Then add its schema and services for
signup, verification, resend, email change, and password reset.

Before any v2 endpoint or runtime authentication wiring, add a typed verified
`access_expired` result and a request-derived transport classifier that rejects
mixed cookie/Bearer credentials and never accepts caller-selected provenance.
Browser cookie wiring must include its CSRF boundary.

The remaining canonical backlog is [ISSUES.md](ISSUES.md).

## Working rules

- Read [CONTRIBUTING.md](CONTRIBUTING.md) before making changes.
- Use only synthetic data, local development, and supported public testnets.
- Never add secrets, private operational artifacts, personal data, production
  identifiers, or private endpoints to this public handover or repository.
- Keep trading disabled and do not deploy or activate runtime RLS as part of
  deferred-hardening work.
- Keep this file short and update it when a checkpoint or next task changes.
