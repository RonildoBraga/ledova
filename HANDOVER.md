# Project handover

Last verified: 2026-09-02

## Current checkpoint

The tenant-isolation audit is complete through PR #37 and
[Issue #1](https://github.com/RonildoBraga/ledova/issues/1) is closed. Guardian
is removed; PostgreSQL RLS activation remains deferred by
[ADR 0002](backend/docs/adr/0002-rls-tenant-isolation.md).

[Issue #2](https://github.com/RonildoBraga/ledova/issues/2) is implemented
through [PR #65](https://github.com/RonildoBraga/ledova/pull/65). PRs #39–#48
landed fail-closed characterization, session rotation/revocation, strict access
JWTs, and active-session binding. PRs #50–#57 froze and implemented the v2
challenge primitives, canonical email boundary, durable schema, and request
source identity. PRs #58–#65 completed the schema correction, logging and query
privacy guards, typed SendGrid adapter, PostgreSQL admission kernel, and atomic
reservation/job coupling.

Base `main` is `963c68656551a0d0dbbab463479f2efa119a31f6`. Independent exact-diff
reviews passed for the queue-coupling batch, and
[post-merge CI](https://github.com/RonildoBraga/ledova/actions/runs/33618762165)
passed every JavaScript, Django, SQLite, and PostgreSQL stage. The v2 delivery
task remains fixed-fail on an excluded hold queue: no provider worker, v2
endpoint, CSRF boundary, client cutover, or legacy retirement is active.

## Next work

Add a disjoint, kernel-owned new-challenge path without weakening the existing
`challenge is locked_scope` proof. The smallest first batch should create a
password-reset challenge for an exact pre-clock locked user, derive all UUIDs
and timestamps in the kernel, and roll back challenge, delivery, and queue job
together. Keep absent-signup user creation and its uniqueness race as a separate
typed batch.

Then implement authoritative resend and worker claim/finalization before wiring
public endpoints. Runtime authentication still needs request-derived transport
classification, mixed cookie/Bearer rejection, typed `access_expired`, and the
browser CSRF boundary before client cutover.

The remaining canonical backlog is [ISSUES.md](ISSUES.md).

## Working rules

- Read [CONTRIBUTING.md](CONTRIBUTING.md) before making changes.
- Use only synthetic data, local development, and supported public testnets.
- Never add secrets, private operational artifacts, personal data, production
  identifiers, or private endpoints to this public handover or repository.
- Keep trading disabled and do not deploy or activate runtime RLS as part of
  deferred-hardening work.
- Keep this file short and update it when a checkpoint or next task changes.
