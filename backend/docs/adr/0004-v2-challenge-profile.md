# ADR 0004 — Exact v2 challenge profile

Status: Accepted — implementation pending
Date: 2026-09-02
Issue: [#2](https://github.com/RonildoBraga/ledova/issues/2)
Extends: [ADR 0003](./0003-authentication-session-protocol.md)

## Context

ADR 0003 defines the shared session core and explicit browser/native
transports. Challenge credential, delivery, rate, and concurrency choices
materially determine the durable schema, so this profile freezes them before
implementation.

## Decision

Replace user-row plaintext codes with one stable, purpose-bound challenge and
separate delivery generations. Signup and email change use a pending context
plus a six-digit OTP. Password reset uses one high-entropy credential and no
OTP. Plaintext contexts, reset credentials, and OTPs are never persisted.
Purpose is exactly `signup`, `email_change`, or `password_reset`; pending
transport is exactly `browser` or `native` and is immutable.

### Identity and public shapes

V2 accepts at most 254 ASCII email characters and rejects every byte outside
printable `0x20..0x7e` before normalization. Its destination key removes only
U+0020 from both ends with Python `str.strip(" ")`, lowercases the full address
with `str.lower()`, then validates it as an email. It performs no Unicode
normalization, case folding, IDNA conversion, or provider-specific dot, alias,
or plus-tag folding. Django 5.2 `validate_email` semantics define syntax
acceptance; changing that dependency requires compatibility review of the
accepted vectors. New signup and successful email-change rows store this key.
A unique legacy account is contacted at its exact stored address, while its v2
lookup and rate identity use the destination key.

Before v2 endpoint cutover, a migration preflight must reject every stored
address that the frozen normalizer would not accept unchanged, including
non-ASCII, invalid-syntax, non-canonical, and case-insensitively colliding
addresses, without printing any address. Every deployed user writer must use
the v2 normalizer before that migration begins. The atomic migration first
acquires its strongest table lock, then runs the non-disclosing preflight and
installs database checks for printable ASCII plus
`email = Lower(Trim("email"))` and unique `Lower(Trim("email"))` expressions
before releasing the lock. `Trim` means U+0020-only trimming here. PostgreSQL
evaluates the trimmed value under C collation so its ASCII lowercase behavior
matches Python.
Until all three land, an existing-address operation proceeds only if a bounded
query on that exact `Lower(Trim("email")) = destination_key` expression returns
one row; zero or multiple rows take the same non-enumerating path. The
migration intentionally replaces the manager's domain-only normalization
contract and updates every user writer and its legacy characterization.
General profile updates cannot write email.

Signup and email-change initiation always return `202`: browser uses
`{"status":"pending"}` and sets, or preserves when valid, an opaque pending
cookie; native adds the opaque `context` field. Resend returns
`202 {"status":"pending"}` and never changes or echoes the context.
Ineligible, ambiguous, suppressed, and rate-limited initiations without a valid
presented context receive a fresh syntactically valid decoy context with no
database authority. Password-reset initiation always returns
`202 {"status":"accepted"}` and never returns its credential; an eligible
account receives it through email. No public status, body, or error selects a
case-insensitive row with `.first()` or otherwise discloses account existence.

The production pending cookie is `__Secure-ledova-v2-pending`; local HTTP uses
`ledova-v2-pending`. It is host-only, `HttpOnly`, `SameSite=Strict`, scoped to
`/api/v2/auth/browser/`, and has no more than a 3,600-second lifetime. Production
sets `Secure`; browser responses never contain the context. Native responses
contain it only when issued and use `Cache-Control: no-store`. The initiating
browser or native route fixes the transport immutably; resend and confirmation
cannot change it.

An unauthenticated repeat signup never changes an incomplete user's password
and never reveals an existing live context. Possession of that context may
resend. After it expires, only proof of the unchanged stored password may issue
a new context for that incomplete user. Complete and ineligible existing paths
perform one dummy password hash before returning a decoy; a genuinely absent
address performs equivalent work while creating the new user's password hash.
A repeated signup never replaces the stored password.

### Credentials and digests

Pending contexts use `lpv2.` and password-reset credentials use `lpw2.`. Each
prefix is followed by exactly 64 canonical, unpadded base64url characters
encoding 48 bytes: the 16 bytes of an RFC 4122 UUIDv4 selector followed by an
independently generated 32-byte secret. Reject non-ASCII, padding, the wrong
prefix, length, alphabet, UUID version or variant, trailing material, and any
value that does not survive decode/re-encode equality before database access.
The selector is exactly the challenge's immutable UUID primary key.
The reset email places `lpw2` only in the client-side fragment of an approved
URL; the client submits it in a request body. It never appears in a query or
server-visible path. This exception uses a dedicated HTTPS bootstrap with no
third-party code, frames, telemetry, or storage access before it reads the
fragment and immediately calls `history.replaceState`. It sets
`Referrer-Policy: no-referrer`, `Cache-Control: no-store`, and a restrictive CSP
allowing only its first-party script and exact API connection. The credential
then remains only in memory until success, terminal rejection, page exit, or
expiry; a password-policy error may reuse it for a corrected submission.

An OTP is exactly six ASCII digits. Generate it by zero-padding an injected
cryptographically secure `randbelow(1_000_000)` result; modulo reduction and a
runtime bypass value are forbidden.

Use HMAC-SHA256 and store exactly 32 digest bytes plus the immutable key ID.
Comparison is constant-time. For bytes `x`, define `frame(x)` as its four-byte
unsigned big-endian length followed by `x`; the HMAC message is the concatenated
frames. Strings below use ASCII and UUIDs use their 16 raw bytes. The five
domains and fields are:

- `ledova:v2:challenge:pending-context`, purpose, challenge UUID, destination
  key, context secret;
- `ledova:v2:challenge:otp`, purpose, challenge UUID, delivery UUID,
  destination key, six OTP bytes;
- `ledova:v2:challenge:password-reset`, challenge UUID, delivery UUID,
  destination key, purpose, reset secret;
- `ledova:v2:challenge:destination-rate`, destination key; and
- `ledova:v2:challenge:ip-rate`, address family, prefix length, packed network
  bytes.

Challenge proof and rate identity use separate keys, initially
`V2_CHALLENGE_PROOF_HMAC_KEY_B64` with key ID
`ledova-v2-challenge-proof-hmac-sha256-1`, and
`V2_CHALLENGE_RATE_HMAC_KEY_B64` with key ID
`ledova-v2-challenge-rate-hmac-sha256-1`. Each value is canonical padded
base64url decoding to at least 32 bytes. They must differ from each other and
from every Django, access, and refresh key in raw and configured textual form.
Bytes never change beneath a key ID, duplicate bytes under different IDs are
rejected, and representations and errors are redacted.

Runtime uses one immutable, injectable `ChallengeKeyConfiguration` containing
current proof and rate writer IDs and keys plus read-only accepted proof and
rate maps. Each current ID must select its exact writer key. Construction
rejects malformed IDs, short or duplicate keys, and reuse against the complete
accepted access-verifier map, refresh keys, challenge maps, and Django secret
in raw, padded, or unpadded configured form. The two environment values above
construct only the initial single-key configuration; rotation supplies both
maps through reviewed process configuration. Its representation and every
configuration error are fixed and redacted.

Challenge key IDs use `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`. A live proof row
whose key ID is absent from the accepted proof map is a configuration invariant
failure; verification never falls back to the current writer key.

Rotation deploys old and new verification keys before switching writers. A
proof key remains accepted until no live row references it and at least 3,720
seconds after its final issuance. During rate-key overlap, every reservation
computes, locks, and queries destination and IP aliases under every accepted
rate key; the old key remains available for at least 3,720 seconds after the
last reservation written with it. Rotation therefore cannot reset a live cap.

### Delivery, limits, and time

A challenge is `open`, then exactly one of `consumed`, `exhausted`, `expired`,
`superseded`, or `invalidated`. A delivery is `reserved`, `sending`,
`ambiguous`, or `active`, then exactly one of `rejected`, `abandoned`,
`suppressed`, `superseded`, `consumed`, `exhausted`, `expired`, or
`invalidated`. A challenge has at most one active and one in-flight delivery.
Resend never changes its context or resets its cumulative OTP failures.

Provider-path delivery transitions are `reserved` to `sending`; `sending` to
`active`, `rejected`, or `ambiguous`; and any in-flight state to `abandoned` at
its lease. Accepted replacement changes the old `active` delivery to
`superseded` while activating the candidate in the same transaction. A
suppressed reservation is terminal and never contains a credential digest.

Successful proof changes the challenge and winning active delivery to
`consumed` and invalidates any in-flight candidate. The fifth OTP mismatch
changes the challenge and active delivery to `exhausted` and invalidates any
in-flight candidate; that challenge blocks a new same-user/purpose challenge
until its original expiry. Challenge expiry changes every nonterminal delivery
to `expired`. Only an authenticated email-change initiation for a different
target may `supersede` an open challenge, and it supersedes every nonterminal
delivery. Explicit cancellation, user ineligibility, a target uniqueness race,
or a conflicting account-security lifecycle makes the challenge and every
nonterminal delivery `invalidated`. Late workers revalidate these coupled
states under lock and cannot revive them.

The public request persists a reservation, queues only its delivery UUID, and
returns; provider latency therefore cannot reveal eligibility. A worker claims
that row, generates its OTP or reset secret in memory, persists only the digest
while committing `sending`, then calls the provider outside the transaction.
Only the worker that changes a locked, live `reserved` row to `sending` may
call the provider; duplicate jobs exit without generating a credential. No
queue payload or database row contains the plaintext credential. It revalidates
account, challenge, candidate, and lease before sending and again under lock
before any activation.

The v2 provider adapter returns only the typed result `accepted`, `rejected`,
or `ambiguous`; it never derives state by parsing an error string. The current
SendGrid client's collapsed result must be replaced before this worker lands.
Only an explicit SendGrid HTTP `202` is `accepted`; it activates the
still-current candidate and atomically supersedes the prior active delivery. A
local pre-send failure or explicit `4xx` is `rejected`. Timeout, connection
loss, `5xx`, or an unexpected response is `ambiguous`. Neither rejected nor
ambiguous delivery replaces the old credential. Provider acceptance means only
that SendGrid accepted the request, not that an inbox received it.

An in-flight row has a lease ending exactly 120 seconds after reservation and
blocks another candidate while `now < lease_expires_at`. At equality it is
atomically abandoned and a new reservation may compete under the normal caps.
A late result never activates an abandoned candidate. No automatic resend is
attempted, and a provider idempotency key is used only if its reviewed contract
actually supports one.

Production captures PostgreSQL `clock_timestamp()` exactly once, after every
advisory and row lock required for that operation is held. That captured value
sets every timestamp and decides reservation, lease, cooldown, expiry, and
rolling-window boundaries; transaction-start and application-node clocks are
forbidden. Tests inject the same post-lock clock interface. A challenge and its
pending context expire 3,600 seconds after initial creation, and resend never
extends them. An accepted OTP is valid for 600 seconds and an accepted reset
credential for 1,800 seconds, each capped by challenge expiry. Proof is valid
only while `now < expires_at`.
Cooldown blocks while `now < accepted_at + 60 seconds`; equality permits
resend. The fifth structurally valid but wrong OTP after a valid context
exhausts the challenge under lock; a correct OTP after four failures may still
win. Malformed OTPs, malformed or unknown contexts, and unknown selectors do
not mutate a row. A wrong 256-bit reset secret also does not mutate a row: an
attempt counter provides negligible protection but would let disclosure of its
selector deny the legitimate reset.

The rolling rate window normally is `(now - 3,600 seconds, now]`; a row at the
lower boundary is excluded. The query has no upper timestamp filter, so a row
later than the captured database time after a clock correction counts
fail-closed until it ages out. An admitted reservation consumes capacity for
the full window whether it becomes accepted, rejected, ambiguous, suppressed,
or abandoned. The fifth total delivery to a destination across all purposes is
allowed and the next is denied; within that total, the third password-reset
delivery is allowed and the next reset is denied. The twentieth admitted
initiation or resend attempt from one source identity across all challenge
routes is allowed and the next is denied. Every syntactically valid signup,
email-change, and reset initiation attempts destination and IP admission before
account eligibility is resolved.
An admitted ineligible, ambiguous, or decoy path becomes `suppressed`; a
capacity-refused path creates no rate row. Both return their endpoint's fixed
public response. Resend with an authoritative context attempts both identities
before eligibility; a decoy or unknown context has no recoverable destination,
so it performs the fixed dummy destination HMAC, attempts the IP cap, and can
never queue delivery. It therefore neither consumes nor bypasses a real
destination's delivery allowance.

Reservation acquires sorted PostgreSQL transaction advisory locks derived from
every accepted-key alias for the destination and IP, then counts and inserts in
one transaction. A plain count followed by insert is invalid. Every new writer
knows the old alias during rotation, so old and new processes share a lock.
The lock ID is the first eight digest bytes interpreted as a signed big-endian
integer; deduplicate and sort those integers before locking. Hash collisions
may over-serialize but never bypass a cap. PostgreSQL race tests are required;
SQLite cannot prove this boundary. A lock-wait regression must start an older
transaction first, let a newer transaction commit while it waits, and prove
that admission and expiry use the older transaction's post-lock database time.

Trust forwarding headers only when the direct `REMOTE_ADDR` is in an exact,
startup-validated trusted-proxy CIDR list. A valid untrusted direct address is
the client identity and any forwarding header is ignored. For a trusted direct
peer, parse at most 2,048 ASCII bytes and ten comma-separated forwarded hops,
right-to-left to the first untrusted address. Only an invalid or missing direct
address, or a malformed, overlong, missing, or all-trusted chain behind a
trusted peer, uses one fail-closed unknown bucket. Collapse IPv4-mapped IPv6,
rate IPv4 by `/32` and IPv6 by `/64`, and HMAC only the family, prefix length,
and packed network bytes. The `/64` choice accepts possible shared-network
false positives to resist IPv6 address churn. Family and prefix length are
unsigned single bytes: `4, 32` for IPv4; `6, 64` for IPv6; and `0, 0` with empty
network bytes for unknown.

### Confirmation responses

Successful signup confirmation returns `200` using the browser or native
credential shape defined in ADR 0003. Browser returns credentials only through
v2 session cookies, clears legacy and pending cookies, and rotates CSRF as ADR
0003 requires; native receives only its new pair and safe session metadata.
Successful email change and password reset return
`200 {"status":"reauth_required"}`, issue no credential, and require both
clients to clear product credentials; browser clears its product and pending
cookies.

Malformed proof, unknown or decoy selector, wrong OTP or reset secret,
pending/ambiguous delivery, expiry, exhaustion, replay, and target-uniqueness
races all return `400 {"code":"challenge_invalid"}`. A failed browser response
does not mutate its pending cookie, so a retryable wrong OTP and an unknown or
terminal context have the same observable cookie behavior; the fixed original
expiry clears it. Missing-row paths perform one domain-correct dummy HMAC and
constant-time comparison with fixed non-secret material. No failure issues a
session or reveals remaining attempts, delivery state, or account existence.
A correct reset proof followed by password-validator failure instead returns
`400 {"code":"password_invalid"}` with bounded policy errors and leaves the
proof active; possession has already established control of the destination.

### Retention, locking, and outcomes

Only an open email-change challenge stores its canonical target address.
Signup and reset derive the exact delivery address from the locked user; an
unknown reset stores only keyed rate evidence. Delivery rows never store raw
destinations, IPs, contexts, OTPs, provider payloads, or target addresses.
Challenge models are absent from admin and use redacted representations; raw
values, selectors, and digests never enter logs, metrics, or errors. Clear the
email-change target in the same transaction as every terminal transition; a
15-minute cleanup marks expired challenges and clears missed targets. Delete
delivery evidence 3,720 seconds after reservation and terminal challenge rows
only after their linked delivery evidence becomes eligible, and within 24
hours. Deleting a challenge must not cascade-delete younger rate evidence; a
delivery retains its purpose and permits a null challenge link.

Transactions that reserve capacity acquire sorted rate advisory locks before
row locks. No other transaction may acquire a rate lock. The row-lock order is
`CustomUser` rows by primary key, challenges by UUID, deliveries by UUID,
sessions by UUID, refresh credentials by UUID, then legacy token rows. Unlocked
topology reads are only bounded hints and every relationship is revalidated
after locking. Provider finalization begins at the user because capacity is
already reserved.

Signup consumption verifies the user and creates at most one session of the
transport fixed at initiation. Email-change consumption updates the address,
clears the target, revokes every session, and issues none. Password-reset
consumption validates and changes the password, revokes every session, and
issues none. Each outcome is one locked transaction; concurrent or repeated
success cannot issue another session. Signup signing or key-configuration
failure rolls back verification, challenge and delivery consumption, and
session creation, leaving the active proof usable. V2 routes never accept
legacy user-row codes, and legacy routes never accept v2 contexts or
credentials.

## Consequences and implementation gate

This profile adds dedicated proof and rate keys, canonical email enforcement,
short-lived challenge and delivery evidence, an asynchronous typed provider
adapter, and PostgreSQL-serialized rate limits. Those costs make challenge
behavior reproducible across browser, native, worker, and database processes.

Implement strict parsers, digests, key configuration, and deterministic tests
first. Challenge schema and provider-neutral services follow with PostgreSQL
race tests. No v2 challenge endpoint or client cutover occurs before those
batches pass independent review.
