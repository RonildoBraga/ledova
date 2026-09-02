# ADR 0005: Withdraw the v2 session protocol

Status: Accepted (2026-09-03). Supersedes ADR 0003 and ADR 0004, which are
deleted; they were last present at commit `963c686` and in git history before
this change.

## Context

The v2 authentication stream (challenge and delivery models, admission kernel,
request-source identity, delivery queue, SendGrid v2 adapter, Procrastinate
privacy log filter, kid-rotated access tokens, HMAC refresh credentials) added
about 4.7k production and 9.3k test lines with zero runtime callers: no URL,
view, admin, worker queue or client reached it, and ADR 0003 steps 5-11 were
still unbuilt. This is a one-person testnet project.

## Decision

Withdraw v2. Keep the canonical-email slice (`authentication/security/v2_email.py`
and `CustomUserManager.resolve_v2_email`, used by the live sign-in and profile
paths). Harden the legacy `AuthViewSet` in place with simplejwt's token
blacklist (refresh rotation, revoke-all), a CSRF check on the cookie transport,
hashed expiring attempt-capped OTPs and a per-email throttle. One auth path.
