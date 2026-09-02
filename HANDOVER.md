# Project handover

Last verified: 2026-09-02

## Current checkpoint

The tenant-isolation audit is complete through PR #37 and
[Issue #1](https://github.com/RonildoBraga/ledova/issues/1) is closed. Guardian
is removed; PostgreSQL RLS activation remains deferred by
[ADR 0002](backend/docs/adr/0002-rls-tenant-isolation.md).

[Issue #2](https://github.com/RonildoBraga/ledova/issues/2) is implemented
through [PR #48](https://github.com/RonildoBraga/ledova/pull/48). PRs #39–#45
added fail-closed characterization and the session/refresh core; PRs #46–#48
added strict v2 access JWT issuance, verification, and active-session binding.
[ADR 0004](backend/docs/adr/0004-v2-challenge-profile.md) now freezes the exact
locked-challenge contract without wiring a runtime endpoint.

Base main is `c459da00fdc24c3665ea0f843b0bd585ebf45596`. The 297-test backend suite,
PostgreSQL checks, repository checks, independent reviews, and
[post-merge CI](https://github.com/RonildoBraga/ledova/actions/runs/33583492183)
passed. No v2 endpoint, request authenticator, CSRF boundary, client cutover,
or legacy retirement is wired yet.

## Next work

Implement ADR 0004's strict parsers, HMAC framing, redacted key configuration,
and deterministic tests. Then land canonical email enforcement, challenge
schema, the typed email-provider/IP adapters, provider-neutral services, and
PostgreSQL rate/confirmation races in small batches.

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
