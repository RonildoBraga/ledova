# ADR 0003 — One session core with explicit browser and native transports

Status: Accepted — implementation pending
Date: 2026-09-02
Issue: [#2](https://github.com/RonildoBraga/ledova/issues/2)

## Context

The dashboard uses cookies, while the mobile app expects bearer credentials in
response bodies and secure storage. The current shared endpoints blur those
transports. Refresh, logout, CSRF, password changes, email verification, and
stream expiry consequently have inconsistent semantics.

The audit also found an invalid-code path that could reach session issuance.
[PR #39](https://github.com/RonildoBraga/ledova/pull/39) now fails closed and
provides the first endpoint regressions. It does not solve the wider protocol.

The redesign must support immediate revocation, multiple devices, transactional
refresh rotation, browser CSRF protection, native process restoration, and a
safe additive migration from the legacy endpoints.

## Decision

### One stateful session core

Add an `AuthSession` per browser or native installation and a separate
`RefreshCredential` history:

- Access JWTs are short-lived and contain `typ`, `ver`, `sub`, `sid`, `jti`,
  `iat`, `exp`, reviewed issuer, and audience. They contain no roles or tenant
  memberships.
- Every request validates the JWT, active user, and active `AuthSession`. This
  preserves immediate logout and account-disable revocation.
- Refresh credentials contain a public random selector and a 256-bit secret.
  Store only an HMAC digest made with a dedicated pepper; retain consumed
  records until the session's absolute expiry to detect replay.
- Do not store access JWTs or plaintext refresh secrets. New sessions never use
  the legacy `UserToken` raw-token fields.
- Use keys dedicated to access-token signing and refresh HMACs, separate from
  Django's `SECRET_KEY`.

Initial lifetimes are 15 minutes for access, seven days of refresh inactivity,
and 30 days absolute session lifetime. Configuration may shorten these values,
but extending them requires a new review.

### Explicit versioned transports

Add `/api/v2/auth/browser/*` and `/api/v2/auth/native/*`. Both use the same
credential and session services, but neither endpoint infers transport from a
user agent, origin, optional cookie, or caller-supplied client-type field.

Browser endpoints:

- issue credentials only as host-only `Secure`, `HttpOnly` cookies;
- never return access or refresh values in JSON;
- require CSRF on every unsafe request, including anonymous sign-in, signup,
  verification, resend, refresh, and recovery actions; and
- return only safe user/session metadata with `Cache-Control: no-store`.

The versioned access cookie uses `SameSite=Lax` and `Path=/api/`. The versioned
refresh cookie uses `SameSite=Strict` and is restricted to
`/api/v2/auth/browser/`, where both refresh and signout can consume it.
Production uses `__Secure-ledova-v2-access`, `__Secure-ledova-v2-refresh`, and
`__Secure-ledova-v2-csrf`, with no `Domain` attribute and an explicit
secure-cookie setting; safety is not inferred from `DEBUG`. Local HTTP
development uses distinct unprefixed names.

`GET /api/v2/auth/browser/csrf/` sets an HttpOnly CSRF secret cookie and returns
the masked token for the dashboard to keep in memory. The dashboard sends it in
`X-CSRFToken`. Credentialed CORS origins and CSRF trusted origins are exact
allowlists; wildcard credentialed origins are forbidden. This contract assumes
the dashboard and API remain same-site. The CSRF cookie is host-only, `Secure`,
`HttpOnly`, `SameSite=Lax`, and `Path=/api/`. Sign-in, verification, password
change, and signout rotate or clear its secret; the dashboard then bootstraps a
new masked token. A `csrf_failed` response means the view did not run, so the
dashboard may bootstrap and retry that request once. Source-aware
authentication enforces CSRF on every unsafe ordinary API request authenticated
by a v2 cookie; anonymous browser-auth actions enforce it explicitly.

Native endpoints:

- never read or set authentication cookies;
- return only the newly issued access/refresh pair, its expiries, and safe
  current-session metadata;
- accept access only through `Authorization: Bearer`;
- accept refresh only in the native refresh or expired-session signout body;
  and
- set `Cache-Control: no-store` on every credential response.

Requests carrying both browser cookies and a bearer credential are rejected as
ambiguous.

Django Admin retains Django session authentication and its built-in CSRF
boundary as a separate staff control plane. It does not issue or consume v2
product sessions.

### Legacy coexistence and cutover

V2 cookies have distinct names from legacy `access` and `refresh` cookies. V2
issuance expires both legacy cookies, and migration-period signout clears both
sets. A v2 endpoint never accepts a legacy credential.

During additive migration, ordinary `/api/` authentication follows signed or
named versions rather than guessing:

- any bearer credential plus any authentication cookie is rejected;
- when a v2 access cookie exists, validate only v2 and never fall back to a
  legacy cookie if v2 is invalid;
- otherwise accept the legacy cookie temporarily; and
- bearer version is selected by a reviewed JWT `kid` and confirmed by its
  verified `ver` claim; selection of v2 never falls back to legacy.

After browser and native journeys both use v2, disable legacy sign-in,
verification issuance, and refresh together. Existing legacy access remains
compatible only with safe HTTP methods for its maximum lifetime; unsafe methods
return `reauth_required`, and no endpoint extends it. After that interval,
remove the legacy authenticator, routes, cookies, serializer, and plaintext
token storage. Emit only aggregate migration counters without credentials or
identifiers.

### Transactional refresh rotation

Refresh creates exactly one successor:

1. Parse the selector and secret, then lock the credential and session in one
   database transaction.
2. Compare the stored digest in constant time and validate user, session, idle,
   absolute, and credential expiry.
3. Mark the credential used, create and link exactly one successor, then issue
   a new access JWT.
4. Replay of a genuinely issued, consumed native credential revokes the whole
   session. A random wrong secret does not.

Two concurrent refreshes are serialized. Native clients use one shared refresh
promise; a second native use is replay. Browser tabs share cookies, so the
dashboard first acquires an origin-wide Web Lock, then rechecks session state
before refreshing. When Web Locks are unavailable or a request was already in
flight, a correctly authenticated spent browser credential presented within
five seconds marks the session `refresh_confirmation_required` and receives
`409 refresh_raced` with a high-entropy, single-use confirmation nonce. No new
session credential is issued and all ordinary use of that session is blocked.
The nonce is returned only in that response body, never a URL or log, and its
digest is stored bound to the session and spent predecessor. The losing tab
waits for the winning cookie update, then calls the browser confirmation
endpoint with the nonce. `POST /api/v2/auth/browser/refresh/confirm/` requires
CSRF, and the HttpOnly cookie must contain the exact unused successor linked to
the spent credential. Confirmation never accepts the access cookie. A correct
proof within ten seconds unblocks the session and consumes the nonce. A wrong,
missing, late, or unconfirmed proof revokes it and invalidates the nonce.

Only the first spent-predecessor collision can enter confirmation. Any further
presentation while confirmation is pending, or any attempt to re-enter after
confirmation or timeout, revokes immediately. Reuse outside the initial
collision window also revokes immediately.

This proves that a benign race's winning response reached the same browser. If
a thief won elsewhere, the legitimate browser cannot present the successor and
the session fails closed before either side can continue using it.

Clients never retry an uncertain refresh POST and retry each original request
at most once. A lost native refresh response requires sign-in. PostgreSQL
concurrency and browser multi-tab tests are required; SQLite cannot prove these
invariants.

Stable error codes such as `access_expired`, `session_revoked`,
`refresh_expired`, `refresh_raced`, `refresh_reused`, `csrf_failed`, and
`reauth_required` drive client state. The collision state and confirmation
timeout are persisted and tested, not held only in one process. English
messages do not drive state.

### Client session coordinators

The dashboard keeps cookie authentication and gains:

- a single-flight CSRF bootstrap, tab-local request queue, and origin-wide
  refresh coordinator;
- `checking`, `authenticated`, `unauthenticated`, and `indeterminate` states so
  network or server failures are not presented as logout;
- identifier-free cross-tab session events; and
- identity-scoped cache and SSE cleanup only after confirmed session changes.

The mobile app gains one `AuthSessionProvider` and one versioned secure-store
record. It keeps access tokens in memory, atomically replaces the refresh record
after rotation, restores a process by refreshing once, and clears malformed or
partial records. A random installation ID may persist across accounts; session
credentials may not. Reusable account passwords are removed from device
storage, and v2 cutover deletes the legacy access/refresh keys before saving the
new record. Issue #13 still owns device-level backup, accessibility, and
supported build validation.

### Session lifecycle

- Current-session signout is explicit, idempotent, and never falls back to
  signout-all when a credential is absent. It also disables that session's push
  registration.
- Signout-all is a separate action requiring current access and recent password
  proof until a general step-up mechanism exists.
- Password change requires the current password; change and reset run Django
  password validators, revoke every session, and require sign-in again.
- Email changes leave the old address active until a challenge proves the new
  address; confirmation updates it atomically, revokes every session, and
  requires sign-in again. General profile updates cannot directly change email.
- Account deletion requires recent reauthentication and revokes sessions and
  push registrations as part of its committed lifecycle. It uses a one-time
  recovery handle and idempotency key whose PII-free terminal result remains
  queryable for 24 hours, so a lost success response can be resolved safely.
- Successful signup verification creates a session before onboarding is
  complete. A verified user may sign in to resume onboarding; incomplete
  onboarding is enforced by route and API authorization, not by denying login.
- Browser logout is not reported complete after a network/server failure.
  Native local logout clears unusable local credentials immediately but reports
  when server revocation is unconfirmed.

Session-list responses expose only bounded metadata: session ID, client type,
sanitized device label, creation/last-use times, and whether it is current.

### Email challenges

Replace user-row plaintext codes with locked, purpose-bound challenge records
for signup, email change, and password reset. Signup returns an opaque
pending-verification context and no session. Browser state uses a short-lived
pending cookie; native state uses the opaque context. Neither client persists
the signup email as the authority for verification. Password reset uses a
high-entropy one-time secret rather than a six-digit code.

Signup and email-change OTPs are six digits, HMAC-protected with a dedicated
pepper, valid for ten minutes, limited to five attempts, and subject to a
60-second resend cooldown. Combined initial, resend, and replacement delivery
caps are five per normalized destination and 20 per IP per hour. Responses do
not enumerate accounts. Correct consumption and session creation occur in one
locked transaction, so simultaneous submissions create at most one session.

Repeated signup cannot replace an incomplete account's password without proof.
Resend activates a replacement only after delivery is accepted, so provider
failure does not destroy the prior usable challenge. The runtime `000000`
bypass is removed; tests inject deterministic code generation instead.

Password-reset initiation always returns the same `202`, whether the address is
known or not. For an eligible account it creates a HMAC-protected 256-bit secret
valid for 30 minutes, limited to five failed confirmations, three sends per
destination and 20 per IP per hour. Confirmation locks and consumes the
challenge, validates and changes the password, and revokes every session in one
transaction. It never issues a session; success returns the user to sign-in.

### Streaming, output, and logs

Issue #2 defines stream lifetime: a stream closes at access expiry and checks
session/user activity on each heartbeat, bounding revocation delay to one
heartbeat. Clients reconnect only through their session coordinator.

Issue #3 performs the transport cutover after the native coordinator exists:
browser EventSource uses its cookie, native SSE uses an Authorization header,
and the query-token fallback is removed. No bearer or replacement ticket may
appear in a URL.

Authentication code never logs credentials, cookies, authorization headers,
codes, request bodies, full Axios errors, or raw query strings. Browser
responses never contain tokens; native responses contain only the newly issued
pair. Issue #12 owns the repository-wide provider/logging audit beyond this
boundary.

## Delivery sequence

1. Keep PR #39's fail-closed verification regressions.
2. Add named legacy characterization tests for browser/native endpoint shapes,
   refresh, logout, password, verification, and SSE behavior.
3. Add session and refresh-history schema plus service and PostgreSQL race tests
   without changing endpoints.
4. Add the locked challenge model and v2-compatible signup, verification,
   resend, and reset services before either client moves. Successful
   verification must issue only the requested v2 transport.
5. Add v2 browser endpoints, source-aware authentication, CSRF enforcement,
   current-session signout, and the dashboard coordinator. Cut over only after
   its complete signup-to-authenticated-to-signout journey passes.
6. Add v2 native endpoints, atomic storage/provider migration, and remove saved
   passwords. Cut over only after the same journey, including current-session
   signout, passes.
7. Land signout-all, password, email, account, and push-session lifecycle
   batches.
8. Complete Issue #3's SSE header/cookie migration and revocation checks.
9. Disable legacy issuance and refresh, force one sign-in, wait out the maximum
   legacy access lifetime, then remove hybrid authentication, raw-token
   serialization/storage, old routes, and compatibility tests.
10. Run an independent cross-client, CSRF, concurrency, secret-output, and
    session-lifecycle audit before closing Issue #2.

Each numbered implementation area is split into reviewable regression-backed
pull requests. Legacy routes coexist only while a named client still requires
them; v2 is never selected through a flag on a legacy endpoint.

## Alternatives rejected

- **Patch the hybrid endpoints in place:** keeps ambiguous credential priority,
  response shapes, and logout/refresh semantics.
- **Store browser bearer tokens in web storage:** simplifies CSRF but exposes
  reusable credentials to JavaScript and XSS.
- **Use Django sessions for browsers and JWT sessions for native:** gives two
  revocation and device models for every lifecycle operation.
- **Use fully stateless JWTs plus a blacklist:** makes immediate per-device
  revocation and refresh-family replay harder while this application already
  performs a database lookup per request.
- **Let a client-type field choose token delivery:** allows caller-controlled
  input to select whether secrets appear in cookies or JSON.
- **Reissue a successor during a replay grace window:** improves retry
  convenience but gives a replay another credential. The browser collision
  response deliberately issues nothing and expires after five seconds.
- **Put SSE bearer or one-time credentials in URLs:** scoped credentials can
  still enter histories, proxies, and observability systems.

## Consequences and completion gate

The design adds a database lookup to authenticated requests, persisted session,
refresh-history and challenge state, CSRF coordination, and a one-time forced
sign-in when legacy sessions are retired. Strict rotation also favors security
over transparent recovery from a lost refresh response.

In return, browser and native behavior is explicit, raw server-side tokens are
eliminated, revocation is immediate, and refresh replay and device lifecycle
become testable invariants.

Issue #2 remains open until both clients use v2, legacy credential paths and
plaintext token storage are removed, PostgreSQL concurrency and cross-client
tests pass, and an independent review finds no unresolved high-severity gap.
