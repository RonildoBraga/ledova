# Project handover

Last verified: 2026-09-02

## Current checkpoint

The application-layer tenant-isolation and authorization audit is complete.
PRs [#21](https://github.com/RonildoBraga/ledova/pull/21) through
[#37](https://github.com/RonildoBraga/ledova/pull/37) are merged, and
[Issue #1](https://github.com/RonildoBraga/ledova/issues/1) is closed.

The work replaced Guardian grants with live ownership, removed Guardian,
self-scoped customer APIs, and bounded global operator access. PostgreSQL RLS
activation remains deferred by
[ADR 0002](backend/docs/adr/0002-rls-tenant-isolation.md).

The authentication audit's first containment is also merged in
[PR #39](https://github.com/RonildoBraga/ledova/pull/39): invalid verification
details now fail before session issuance. At merge commit
`57a109464ca3b3820a289f8b99648bded70fd555`, 199 credential-free Django tests,
48 PostgreSQL tenancy tests, repository checks, independent review, and
[post-merge CI](https://github.com/RonildoBraga/ledova/actions/runs/33571636624)
all passed.

## Next work

Continue [Issue #2](https://github.com/RonildoBraga/ledova/issues/2) by
implementing
[ADR 0003](backend/docs/adr/0003-authentication-session-protocol.md) in its
dependency order. Start with named legacy characterization tests, then use
small focused PRs with regressions and independent review.

The remaining canonical backlog is [ISSUES.md](ISSUES.md).

## Working rules

- Read [CONTRIBUTING.md](CONTRIBUTING.md) before making changes.
- Use only synthetic data, local development, and supported public testnets.
- Never add secrets, private operational artifacts, personal data, production
  identifiers, or private endpoints to this public handover or repository.
- Keep trading disabled and do not deploy or activate runtime RLS as part of
  deferred-hardening work.
- Keep this file short and update it when a checkpoint or next task changes.
