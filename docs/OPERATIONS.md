# Operations

Everything needed to configure, seed, run and upgrade a Ledova deployment:
the operator row, the environment variables, key management, chain
configuration, background jobs, migration notes and the pre-release checks.

Ledova is experimental and unaudited. Run it on a local chain or a supported
public testnet only.

## Operator configuration

The operator is whoever hosts the deployment: a single company running its own
instance, or a registry provider hosting many companies. Its configuration is
one row, `operators.Operator`, edited in the Django admin.

- The admin changelist, `/admin/operators/operator/`, seeds the row if it is
  missing and renders the **operator console** — the configuration health
  strip, the worklist, and the deployment mode with the register keeper for
  each active company — with a button through to the single change page,
  `/admin/operators/operator/1/change/`. Always enter through the changelist:
  the change URL alone redirects to `/admin/` on a fresh install, because
  `changelist_view` is the only thing that creates the row. Add is offered only
  while no row exists; delete never is. One row is enforced three ways: a fixed primary key
  of 1, a `CheckConstraint` on it, and a guard in `save()`.

### The operator console

`/admin/operators/operator/` is the one page that says what is waiting. It adds
no model, no URL namespace and no `AdminSite` subclass: it is
`OperatorAdmin.changelist_view` rendering a template over
`operators/services.py`.

- **Configuration health** fails closed before an offering opens rather than at
  payment-instruction time. Five checks: the operator row carries a name, legal
  name, ABN and contact email; `WHITELIST_CONTRACT_ADDRESS` is set;
  `SHARE_TOKEN_FACTORY_ADDRESS` is set; `payment_reference_prefix` is present
  and at most ten characters, so the prefix plus the eight-character code fits
  the eighteen-character AU lodgement limit; and every supported settlement
  asset holds an active deployment on `receiving_wallet_chain`. A fresh install
  starts with an empty settlement-asset set, which the strip reports rather
  than passing silently — an offering can then only be paid by bank transfer.
- **The worklist** is thirteen labelled counts. Eleven link to the admin
  changelist already filtered; the two register queues link to the whitelist
  changelist unfiltered, for the reason given below. The thirteen are: company
  applications submitted, in review or
  needing information; classifications awaiting verification; offerings
  submitted or under review; offerings whose paid and allotted subscriptions
  have reached the cap while the offering is still open; subscriptions awaiting
  payment; subscriptions paid and not allotted; subscriptions whose mint is
  broadcast and unresolved; whitelist entries pending; issuance and
  capital-increase requests submitted, approved-not-executed or failed; share
  tokens stuck in `DEPLOYING` past the pending-deployment age; and the two
  register queues below. Eleven of them are one `.count()` on an existing
  queryset method; the last two share one identity read. Nothing on the page
  touches the chain, so it cannot hang on a flaky RPC.
- **The two register queues are the operator's only sight of a holder who
  cannot be named.** "Allotment addresses with two wallets, so no member can be
  named" is the `ambiguous` holder type: two `WhitelistEntry` rows on one
  address on the registry network, which only the operator can resolve, since
  `WhitelistService._resolve_wallet` refuses to act on it. "Allotment
  addresses with no member behind them" is `unidentified`: no whitelist entry
  at all, or an entry whose wallet carries no named profile. Both are red,
  because a register row that cannot name a member of the company is a section
  169 defect and the issuer's own token modal is otherwise the only place it
  shows. Both count distinct completed allotment addresses through
  `whitelist/services/identity.py`, the same code the register uses, so a
  holder type means the same thing on both surfaces. They count allotment addresses rather than chain-confirmed register
  rows, so an unidentified former member who has transferred out can still
  appear; the queue is never shorter than the register, which is the safe
  direction. **Neither row can carry a filter, and both land on the unfiltered
  whitelist changelist.** No filter on `WhitelistEntryAdmin` expresses either
  condition, and for `unidentified` none could: its commonest case is an
  allotment address with no whitelist entry at all, so there is no row on that
  changelist to filter to. To clear one: open the whitelist changelist, paste
  the address from the issuer's token modal into the search box, and either
  link the wallet to an account with a named profile, remove the duplicate
  entry, or add the missing entry. The identity read is chunked at five hundred
  addresses a query, so the SQL stays the same size whatever the deployment
  holds; the cost is at most three queries a chunk — the whitelist entries,
  their accounts and the profiles behind them — over one address per member of
  every
  company on the deployment, held in memory. Calling the same identity code as
  the register was preferred to a second definition of the holder types in SQL,
  which could drift from it.
- **Deployment mode and the registrant.** The console names the mode
  (`registry` or `single_issuer`) and, for each active company, who keeps the
  register on this deployment. It states that fact and nothing more: it does
  not assert who carries the section 168 obligation, which is a question for
  the issuer and its advisers.
- The row is created lazily the first time the admin page or
  `GET /api/operator/` asks for it, named from `OPERATOR_NAME` (default
  `Ledova operator`). Nothing in the compose `migrate` chain creates it.
- `Operator.clean()` normalises and validates the ABN (11 digits), the BSB
  (6 digits), the payment reference prefix (2 to 16 letters or digits, upper
  cased) and the receiving wallet address (checksummed EVM address).

| Admin section | Fields |
| --- | --- |
| Identity | `name`, `legal_name`, `abn`, `contact_email`, `website` |
| Deployment | `deployment_mode`: `single_issuer` or `registry` (default) |
| Payments | `bank_account_name`, `bank_bsb`, `bank_account_number`, `payment_reference_prefix`, `receiving_wallet_address`, `receiving_wallet_chain` (`ethereum` or `base`), `issued_stablecoin`, `supported_settlement_assets` |
| Eligibility | `investor_kyc_required` (default on), `issuer_kyc_required` (default off) |
| Timestamps (collapsed, read-only) | `created_at`, `updated_at` |

`issued_stablecoin` and `supported_settlement_assets` accept only `assets.Asset`
rows of type `stablecoin`, and each must hold an active `AssetChainDeployment`
carrying a contract address on `receiving_wallet_chain`. The model refuses the
first on save; the change form refuses the second, because a many-to-many is
not saved when `Model.clean()` runs. `operators/settlement.py` is the one
resolver: `settlement_assets()`, `deployment_for()` and `require_deployment()`.
Never read `Asset.contract_address` for settlement — it returns the
alphabetically first chain, so it silently prefers `base` over `ethereum`.

`payment_reference_prefix` is capped at 10 characters, so the prefix plus an
eight-character code fits the 18-character AU lodgement reference.

`GET /api/operator/` (authenticated; 401 for anonymous) returns `name`,
`legalName`, `abn`, `contactEmail`, `website`, `deploymentMode`,
`supportedSettlementAssets`, `issuedStablecoin`, `investorKycRequired`,
`issuerKycRequired` and `paymentInstructions`.

`paymentInstructions` is served only to staff and to a caller the investor
eligibility predicate accepts for at least one company; every other
authenticated caller gets `null` there, and the rest of the payload unchanged.
When it is served it carries only the payment fields that are set (and the
chain only when the wallet address is set). Turning the bank details on for a
new deployment is therefore two things: filling them in on the operator row, and
having verified investor classifications for the people who need to read them.

The two eligibility switches are configuration for a later phase. No gate reads
them yet. `single_issuer` disables the supporting-payslip store: its profile
panel, every document API and admin read, uploads and extraction. Classification
claims keep their existing evidence upload and human review. The operator form
refuses a switch to single issuer while unpurged payslips exist; retained content
must first be handled under its retention policy. A missing operator row uses
the existing registry default; document permission checks do not create it.

## Environment variables

Every backend variable below is read in `backend/ledova_backend/settings/`; the
client and contract variables are at the end of this section.
`backend/.env.example` is the template; `python3 scripts/init-local-env.py`
(also `make init-local`) copies it and the three client templates to
owner-only `.env` files and fills `SECRET_KEY` and `POSTGRES_PASSWORD` with
generated secrets. It never overwrites an existing file.

`DEBUG`, `COOKIE_SECURE` and `EVM_ASSET_TRANSFER_HISTORY_ENABLED` go through
`read_bool`, which strips and lowercases the value first, so `true`, `TRUE` and
` true ` are all accepted, and must resolve to `true` or `false`; anything else
raises `ImproperlyConfigured` at startup. `KYCAID_CRYPTO_MONITORING_ENABLED` is
compared against the literal `true` and treats anything else as off.

### Django core

| Variable | Default | Required |
| --- | --- | --- |
| `SECRET_KEY` | none | Yes, startup fails without it |
| `DEBUG` | `false` | No |
| `DJANGO_ALLOWED_HOSTS` | empty | Yes outside local use, comma separated |
| `DJANGO_CORS_ALLOWED_ORIGINS` | empty | Yes, comma separated; must list the dashboard origin |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | empty | Yes, comma separated; cookie-authenticated writes from an unlisted origin get `403 CSRF Failed` |
| `LEDOVA_ADMIN_BASE_URL` | `http://localhost:5174/admin` | No |
| `PUBLIC_API_BASE_URL` | `http://localhost:8000` | No |
| `OPERATOR_NAME` | `Ledova operator` | No, used only when the operator row is created |
| `REDIS_URL` | `redis://redis:6379/0` | **Yes.** It is `CACHES["default"]`, which holds the sign-in and upload quotas, and it is the trading event stream (`tokens/events.py`, `tokens/views/trading_events.py`). Background work is still Procrastinate on PostgreSQL |

The per-address sign-in limit is 10 attempts in a rolling hour, shared by all
backend workers through `CACHES["default"]`. `SharedRedisCache` reserves each
attempt atomically in Redis using Redis's clock. Simultaneous requests cannot
overwrite each other's counts. Successful and unsuccessful credential checks both
consume an attempt; requests already over the limit return 429 with `Retry-After`.
The count survives backend worker restarts and deployments. Redis data loss or an
explicit cache clear resets it; the Compose volume alone is not a durability
guarantee for every Redis failure.

Redis is required for sign-in. An unreachable cache returns 503 with "This service
is temporarily unavailable. Please try again shortly." before checking credentials.
Backend and worker containers wait for the Redis healthcheck. Trading event streams
handle their own Redis failures and continue to degrade independently.

The default cache also holds the Transak access token
(`integrations/transak/client.py`), which is now shared between workers. Other DRF
rate limits use this shared cache but retain DRF's approximate read/write counting;
the strict atomic rolling windows apply to `auth_email` and uploads.

Ordinary test settings retain `LocMemCache`. CI separately runs the deployed cache
against a real Redis service, including fresh processes, concurrent sign-in
requests, window expiry and a connection failure. Run that suite locally with an
isolated Redis URL:

```sh
THROTTLE_TEST_REDIS_URL=redis://127.0.0.1:6379/15 \
  python manage.py test authentication.tests.redis_throttle \
  --settings=ledova_backend.settings.test --noinput
```

The Redis suite requires its URL and fails if Redis is unavailable. It deletes
only its own unique test keys and stops its child processes on completion.
The concurrent test holds real history reads until all requests have read the
same state, exposing lost updates if DRF's read/write implementation returns.

### Auth cookies and tokens

| Variable | Default | Required |
| --- | --- | --- |
| `COOKIE_ACCESS_NAME` | `access` | No |
| `COOKIE_REFRESH_NAME` | `refresh` | No |
| `COOKIE_DOMAIN` | unset | No; also scopes `csrftoken`. Leave empty for localhost, set the shared parent domain when dashboard and API are on different subdomains |
| `COOKIE_SECURE` | the opposite of `DEBUG` | No |
| `ACCESS_TOKEN_LIFETIME` | `604800` seconds | No |
| `REFRESH_TOKEN_LIFETIME` | `604800` seconds | No |

A seven-day access token is safe here because it carries its refresh jti
(`rjti`) and every request checks the session is still live, so revocation is
immediate. Remove any older `ACCESS_TOKEN_LIFETIME=86400` override to pick the
default up.

### Database

| Variable | Default | Required |
| --- | --- | --- |
| `POSTGRES_HOST` | none | Yes |
| `POSTGRES_PORT` | none, so libpq's own default applies | No |
| `POSTGRES_DB` | none | Yes |
| `POSTGRES_USER` | none | Yes |
| `POSTGRES_PASSWORD` | none | Yes |
| `POSTGRES_SSLMODE` | `prefer` | No |

The connection is configured with `CONN_MAX_AGE` 300 seconds, a 10 second
connect timeout and TCP keepalives.

Compose sets `POSTGRES_HOST` to `postgres`, `REDIS_URL` to
`redis://redis:6379/0`, `STORAGE_BACKEND` to `local` and `DEBUG` to `true` for
the `migrate`, `backend` and `worker` services, from one `x-backend-environment`
anchor so the three cannot drift. These are `environment:` entries, so they win
over `backend/.env`: a `STORAGE_BACKEND=s3`, a `DEBUG=false` or a custom
`REDIS_URL` in that file is silently ignored inside the local stack. The local
stack explicitly selects debug mode; uploaded evidence uses private storage
and authenticated routes in both debug modes.

`backend/.env` is still needed: `SECRET_KEY` and `POSTGRES_PASSWORD` come only
from it, and no committed file can supply them. Without it `postgres` refuses to
initialise and `migrate` dies on `KeyError: 'SECRET_KEY'` before anything
serves requests. Run `make init-local` first; `make dev-up` checks.

### Blockchain

| Variable | Default | Required |
| --- | --- | --- |
| `BLOCKCHAIN_RPC_URL` | `ALCHEMY_BASE_URL` if set, else `http://localhost:8545` | Yes for any chain call |
| `BLOCKCHAIN_CHAIN_ID` | `84532` | No; must be one of 1337, 31337, 84532, 11155111 or startup fails |
| `ETHEREUM_CHAIN_ID` | `11155111` | No; same allowed set |
| `BITCOIN_NETWORK` | `test` | No; `test` or `regtest` only |
| `EVM_ASSET_TRANSFER_HISTORY_ENABLED` | `false` | No; without it EVM holdings appear only from app-initiated transfers |
| `BLOCKCHAIN_OPERATOR_KEY` | empty | Yes to deploy, mint, whitelist, pause |
| `WHITELIST_CONTRACT_ADDRESS` | empty | Yes for issuance |
| `SHARE_TOKEN_FACTORY_ADDRESS` | empty | Yes for issuance |
| `ATOMIC_SWAP_ADDRESS` | empty | Only for settlement |
| `STABLECOIN_CONTRACT_ADDRESS` | empty | Only for stablecoin payment; seeds the `AUDY` deployment on `base` |
| `SWAP_ORDER_EXPIRY_HOURS` | `0.25` (15 minutes) | No; finite fractional hours are accepted |

Malformed and non-finite values are refused at settings import. This default
applies when issuing a new swap without an explicit signing window.
Existing stored deadlines and signatures are preserved. An explicit operator
override still takes precedence: remove an older `SWAP_ORDER_EXPIRY_HOURS=24`
override or set it to `0.25` to use the new default for future swaps. The ordinary
order-challenge lifetime remains 300 seconds.

### Data retention

| Variable | Default | Required |
| --- | --- | --- |
| `CLASSIFICATION_EVIDENCE_RETENTION_DAYS` | `2557` | No; `0` retains indefinitely and purges nothing |
| `UNATTACHED_DOCUMENT_RETENTION_DAYS` | `30` | No; lifetime of an unattached payslip from upload; `0` retains indefinitely |

Days an investor classification's evidence file is kept after the claim is
rejected, revoked or expires. The default is a **placeholder pending counsel,
not advice**: 2557 days is seven calendar years including two leap days.
Australian financial-record and AML/CTF customer-identification obligations are
the constraints to confirm it against. Set `0` while the period is undecided —
the retention deadline remains unset and nothing is deleted. Attached payslips
inherit this same claim clock; unattached uploads use their separate, shorter
lifetime. Neither setting changes an eligibility decision.

### Media storage

| Variable | Default | Required |
| --- | --- | --- |
| `STORAGE_BACKEND` | `local` | No; `local`, `s3` or `gcs`, and forced to `local` whenever `DEBUG` is on |
| `AWS_STORAGE_BUCKET_NAME` | none | Yes when `STORAGE_BACKEND=s3` |
| `AWS_S3_REGION_NAME` | `ap-southeast-2` | No |
| `GS_BUCKET_NAME` | none | Yes when `STORAGE_BACKEND=gcs` |

Uploaded evidence uses private storage and authenticated streaming endpoints.
No upload is served by `/media/`, including in debug mode. Local evidence lives
under `PRIVATE_MEDIA_ROOT`; cloud evidence uses private S3/GCS objects. See the
[storage and retention architecture](ARCHITECTURE.md#uploaded-files).
Local private storage also works with `DEBUG=false`. The obsolete startup guard
that required a public `/media/` route has been removed. Both entrypoints still
require the scoped request connection, and authenticated file reads retain the
same owner and staff permissions.

### Upload validation and resource limits

Uploads require Redis and a running ClamAV daemon with current signatures.
Compose adds `clamav/clamav:1.5.4`, a 4 GiB memory limit, two CPUs and a private
TCP endpoint with no published host port. Backend and worker startup require the
scanner service to start, but do not wait for signature loading or health. Other
application routes remain available; uploads return 503 until scanning succeeds.
The health probe uses `clamdscan --ping=1 --config-file=/etc/clamav/clamd.conf`.
Freshclam updates the dedicated `clamav_data` volume. The checked-in clamd config
rejects over-budget/encrypted content, caps scan time at 5 seconds and refuses
startup with databases older than seven days. Monitor health and Freshclam update
failures; startup freshness is not a continuous freshness guarantee.

ClamAV's [INSTREAM protocol](https://docs.clamav.net/manual/Usage/ClamdProtocol.html)
has no authentication or transport encryption. Keep it on a trusted private
network accessible only to application services. Follow the
[official Docker guidance](https://docs.clamav.net/manual/Installing/Docker.html)
for signature storage and resource provisioning. An exact clean verdict is
mandatory; connection errors, malformed replies and unavailable scanning fail
closed. The client runs in a child with a parent deadline that also covers DNS
resolution. Detected files return 400 and are never saved to permanent storage;
there is no retained quarantine or bypass switch. Malware scanning cannot prove
arbitrary content harmless.

Defaults below are integer environment settings shared by backend and worker.
The decoder uses Linux resource limits; clean synthetic PDF/PNG/JPEG controls run
under the default 512 MiB address-space cap in CI. Resource limits contain work;
they are not a security sandbox or an aggregate concurrency limit.

| Variable | Default | Bound |
| --- | --- | --- |
| `UPLOAD_MAX_BYTES` | `10485760` | Actual bytes per file (10 MiB) |
| `UPLOAD_MAX_REQUEST_BYTES` | file limit + `65536` | Whole upload request before multipart buffering |
| `UPLOAD_BODY_SECONDS` | `30` | ASGI body arrival deadline |
| `UPLOAD_MAX_PDF_PAGES` | `100` | Pages inspected before any rendering |
| `UPLOAD_MAX_SOURCE_PIXELS` | `16000000` | Image/embedded-image pixels or PDF page pixels at 2x scale |
| `UPLOAD_MAX_DECODED_BYTES` | `67108864` | Four bytes/pixel estimate per image/page and sum of unique embedded images on a page |
| `UPLOAD_RENDER_MAX_SIDE` | `1600` | Longest rendered PNG side |
| `UPLOAD_RENDER_MAX_BYTES` | `8388608` | Rendered PNG bytes |
| `UPLOAD_PROCESS_MEMORY_BYTES` | `536870912` | Decoder and scanner-client address space |
| `UPLOAD_PROCESS_CPU_SECONDS` | `5` | Child CPU time |
| `UPLOAD_PROCESS_WALL_SECONDS` | `10` | Decoder child wall deadline |
| `UPLOAD_SCANNER_HOST` | `clamav` | Private daemon hostname; Compose sets this explicitly |
| `UPLOAD_SCANNER_PORT` | `3310` | Private daemon TCP port |
| `UPLOAD_SCANNER_SECONDS` | `10` | Scanner-client child wall deadline |
| `UPLOAD_REQUESTS_PER_HOUR` | `20` | Authenticated create attempts per rolling hour/user across all upload routes |
| `UPLOAD_BYTES_PER_HOUR` | `52428800` | Actual file bytes per rolling hour/user (50 MiB) |

Accepted and rejected authenticated attempts consume quota; quota rejection does
not admit more work. Redis Lua uses the server clock and reserves count/bytes
atomically across processes. File chunks are charged before scanning; files
parsed during successful cookie CSRF authentication are charged before validation.
Authentication/CSRF failures and files refused while authentication is still
parsing have no completed user identity to charge, but have the same body/file
caps. A missing atomic cache implementation or unavailable Redis returns 503;
quota denial returns 429 with `Retry-After`. Worker restarts retain quota;
Redis data loss resets it. Only one file is accepted per request.

The entrypoint bounds apply to resolved upload-create routes, including chunked
ASGI bodies and falsely small declared sizes. WSGI cannot interrupt a blocked
socket read: configure the HTTP server/proxy body timeout. Configure proxy/server
body and connection/concurrency limits for both entrypoints, since unauthenticated
clients and many users can each consume a bounded request. Keep the proxy cap at
least the configured request limit if clients should receive the API error body.
Changing file limits also requires aligning `StreamMaxLength`/`MaxFileSize` and
the other scan limits in `backend/clamav/clamd.conf`; the stricter bound wins.

CI runs synthetic clean formats and EICAR through a real daemon and tests Redis
expiry, unavailable connections, fresh processes and concurrent reservations.
Ordinary unit tests stub these external dependencies explicitly; they do not
establish malware detection. Run the integration suites against isolated services:

```sh
UPLOAD_TEST_CLAMAV_HOST=private-scanner \
  python manage.py test shared.tests.clamav_uploads \
  --settings=ledova_backend.settings.test --noinput
UPLOAD_TEST_REDIS_URL=redis://isolated-redis:6379/0 \
  python manage.py test shared.tests.redis_uploads \
  --settings=ledova_backend.settings.test --noinput
```

The suites require real reachable services and fail if they are unavailable;
Redis tests remove only their own unique keys. This change adds the deployment
dependency; it does not roll out a scanner to an already running dev stack.

### Market data and chain providers

| Variable | Default | Required |
| --- | --- | --- |
| `ALCHEMY_ETH_URL`, `ALCHEMY_BTC_URL`, `ALCHEMY_BASE_URL` | empty | Only for provider-backed sync |
| `ALCHEMY_WEBHOOK_SIGNING_KEY` | empty | Yes to accept `/webhooks/alchemy/` |
| `COINGECKO_API_KEY` | empty | No |
| `COINGECKO_BASE_URL` | `https://api.coingecko.com/api/v3` | No |
| `COINGECKO_TIMEOUT` | `10` seconds | No |
| `BLOCKSTREAM_API_URL` | `https://blockstream.info/testnet/api` | No |
| `BLOCKSTREAM_TIMEOUT` | `30` seconds | No |

Alchemy wallet webhooks must include `event.network`, as supplied by the
[Address Activity payload](https://www.alchemy.com/docs/reference/address-activity-webhook).
`BASE_SEPOLIA` is accepted only with `BLOCKCHAIN_CHAIN_ID=84532`, and
`ETH_SEPOLIA` only with `ETHEREUM_CHAIN_ID=11155111`. Missing, unknown, mainnet,
or locally mismatched networks receive HTTP 400 after signature verification.
Accepted events enqueue each matching wallet on that network, including both
transfer participants and separate accounts sharing an address. Receipt workers
fetch chain state themselves; webhook balances and block numbers are not settlement
evidence.

Manual wallet sync returns `success: false` with an actionable `syncResult.error`
when verification is missing, the provider fails, history cannot be read or a
known holding cannot be refreshed. Both clients display that reason. A partial
refresh keeps any balances it did read, and leaves the wallet's last successful
sync time unchanged.

Wallet import previews use `POST /api/wallets/batch-check-balances/` with an
explicit `userAccount`, `chain` (`ethereum`, `base`, or `bitcoin`) and 1–20
addresses. The account must still belong to the signed-in user; staff status
does not bypass membership. Addresses need not be registered yet. The response
repeats the account and network and returns `balances[address]` as a decimal
string or `null` when the provider cannot supply a valid balance. A confirmed
zero remains `"0"`. Preview reads do not create or update wallets or holdings.
Both clients display failed reads as **Unavailable** and discard pending
responses when the selected account or network changes. Hardware and software
import screens let the user choose Ethereum or Base for their EVM addresses.

Alchemy transfer history follows each direction's `pageKey` through the final
page, with an explicit newest-first order. Pagination finishes before receipt
lookups, because Alchemy cursors expire after ten minutes. A repeated cursor,
unreadable response or continuation beyond 100 pages per direction fails the
sync rather than presenting a truncated history as complete. See the
[Alchemy pagination contract](https://www.alchemy.com/docs/reference/transfers-api-quickstart).

Pending-transfer deductions record the holding generation they changed. A failure
returns each recorded deduction once, and only while that generation is still
current. An authoritative chain refresh supersedes that deduction; a later
provider outage cannot turn its reversal into an extra balance. Token and native
fee deductions are checked independently. Balance reads run outside row locks,
and observations made across a concurrent holding change are discarded for retry.

Migration `wallets.0012_balance_versions` preserves existing quantities and
recorded deductions. Existing transactions have no provable generation: if such
a transfer fails during a provider outage, its cached balance stays unchanged
until a successful chain refresh. The migration never guesses a refund from an
old declared amount or fee estimate. Optimistic changes do not advance the last
successful chain-sync timestamp.

Confirmation, failure and reorg transitions persist a balance-reconciliation
token before committing. If a worker stops or a balance/snapshot operation fails,
the five-minute sweep requeues that work even after transaction status changes.
Retries complete the balance and snapshot work without repeating notifications
or refunds. A reorg after a successful confirmation sync retains superseded
deductions until an authoritative refresh succeeds. Unavailable providers leave
the repair pending; a later transition prevents an older repair from completing
over it.

### Former-member records

The periodic former-member fold reads every deployed or paused share class every
six hours. It reads through the provider's `finalized` block, using the
[Base RPC block tag](https://docs.base.org/base-chain/api-reference/ethereum-json-rpc-api/eth_getBlockByNumber).
An unavailable finality reading leaves the last successful fold unchanged.
It replays ordered Transfer events from deployment and records each
cessation under that class. If a holder ceases more than once in one block, the
last cessation in that block supplies that record. Incomplete, repeated or
unreadable history leaves the previous successful timestamp intact. Database
writes and the new timestamp commit together after provider reads finish.
A class failure does not stop other classes being processed, but fails the task
after the batch so its retry policy runs again after five minutes, within its
configured retry limit. Refolding a class already processed does not rewrite its records.

The register API and CSV carry a separate former-members section with the last
successful read time, block and stale indicator (24 hours). A class never read
successfully is explicitly stale. The dashboard permits CSV export when all
current holders have left. GET requests do not run or write the fold.

Names and addresses are frozen on the first recorded cessation and are not
looked up again on a refold. The source and recording time accompany those
particulars. A current profile is identified as the profile at recording time;
if it is unavailable, an allotment record dated no later than the cessation may
supply the particulars. Otherwise the identity is marked unknown. This does not
claim to reconstruct profile changes before the first fold.

Former-member rows are readable by the company owner and operator only. Public
visibility of the parent share class does not reveal these rows. The application
role cannot insert, update or delete them. Owner-transfer support would need to
propagate the derived owner column before such a feature is enabled.

`FORMER_MEMBER_RETENTION_DAYS` defaults to 2557, independently of classification
evidence retention. The sweep measures from the cessation date, and a later
full-history fold cannot recreate expired records. A value below 2557 refuses
the fold and purge. This implements the accepted seven-year retention assumption
for s169(3); counsel must settle the legal basis and responsibility for the
register before public use.

Rejected offerings can be withdrawn by their issuer. Withdrawal retains the
reviewer, review time, notes and rejection reason. A withdrawn row remains
visible as a record, including its previous rejection, and offers no further
edit, resubmit or delete action.

### Company registry verification

`ABR_AUTH_GUID` is blank by default. Obtain the free authentication GUID through
[ABR Web Services](https://abr.business.gov.au/Tools/WebServices) and configure it
server-side. With no GUID, review records a pending, unconfigured attempt without
contacting ABR. All test and development inputs must remain synthetic.

Start Review uses each company's confirmation page and POST action; bulk review
is unavailable. Start Review and Retry Registry Check record each ABR attempt,
its input, time and selected entity response. Lookup uses the application
ABN, or its ACN when ABN is blank. Each lookup has a 15-second whole-call deadline,
including DNS and response reads, in a supervised subprocess with a 1 MiB streamed
response cap. The authentication GUID travels through its input pipe, not its
command line or inherited application environment. A discovered ABN is recorded
in the attempt; it does not replace the application identifier. Registered company
names must match after Unicode, case and whitespace normalization. Trading names and fuzzy
matches do not establish identity. Suppressed or unknown responses, missing
records, mismatches, cancelled registrations and provider failures cannot pass.

Company type must match the [ABR entity-type code](https://abr.business.gov.au/documentation/referencedata):
Proprietary Limited requires `PRV`; Public Company and Unlisted Public Company
require `PUB`. ABR does not distinguish listed from unlisted public companies, so
this check does not verify listing status. Missing, ambiguous or unsupported
types remain pending; a contradictory `PRV` or `PUB` result fails verification.

Approval requires a named officeholder declaration, board-resolution reference
and explicit operator attestation. Only operator review pages expose these
details and attempt history. ABR checks the entity's ABN registration; the
officeholder declaration is separate. Correct a registered name during DRAFT or
after Request Information, then resubmit for review. ACN, ABN and company type
remain editable only in DRAFT.

Activate, Resolve Warning and Reinstate each run a fresh lookup outside database
transactions and require a matching pass. Failure retains the attempt and leaves
the prior company status in place; retry the action after resolving the cause.
Legacy APPROVED, WARNING and SUSPENDED companies without an attestation receive
the declaration fields on the same action form. The staff status API accepts
`declarant_name`, `board_resolution_reference` and `attest_officeholder` for
approval and this recovery. Existing ACTIVE companies retain their status when
the migration runs, and a registry retry does not automatically suspend them.
There is no manual registry override or stale-pass fallback.

### KYC providers

Disabled until configured. With `KYC_PROVIDER` blank the integration answers
`503 Service not configured`.

| Variable | Default | Required |
| --- | --- | --- |
| `KYC_PROVIDER` | empty | Yes to enable identity verification |
| `KYCAID_API_TOKEN`, `KYCAID_BASE_URL`, `KYCAID_FORM_ID` | empty | Yes for KYCAID |
| `KYCAID_CRYPTO_MONITORING_ENABLED` | `false` | No |
| `SUMSUB_API_KEY`, `SUMSUB_SECRET_KEY`, `SUMSUB_BASE_URL` | empty | Yes for Sum&Sub |
| `SUMSUB_LEVEL_NAME` | `basic-kyc-level` | No |
| `SUMSUB_WEBHOOK_SECRET` | empty | Yes to accept `/webhooks/sumsub/` |
| `CRYPTO_RISK_THRESHOLD_MEDIUM` | `0.25` | No |
| `CRYPTO_RISK_THRESHOLD_HIGH` | `0.6` | No |

### Email

| Variable | Default | Required |
| --- | --- | --- |
| `DEFAULT_FROM_EMAIL` | `noreply@localhost` | No |
| `SENDGRID_API_KEY` | empty | Yes outside `DEBUG` |
| `SENDGRID_API_URL` | empty | With SendGrid |
| `SENDGRID_TIMEOUT` | `10` seconds | No |

The email backend follows `DEBUG`: the console backend when `DEBUG=true`, SMTP
otherwise. With `DEBUG=true` the sign-up verification code is printed to the
backend log.

### On-ramp

| Variable | Default | Required |
| --- | --- | --- |
| `TRANSAK_API_KEY`, `TRANSAK_API_SECRET`, `TRANSAK_API_URL`, `TRANSAK_API_GATEWAY_URL` | empty | Yes to enable the widget |
| `TRANSAK_REFERRER_DOMAIN` | `localhost` | No |
| `TRANSAK_THEME_COLOR` | `6366f1` | No |

### Document extraction

| Variable | Default | Required |
| --- | --- | --- |
| `LLM_BASE_URL` | `http://host.docker.internal:11434/v1` | No |
| `LLM_MODEL` | `qwen2.5vl:7b` | No |
| `LLM_EXTRA_HOSTS` | empty | No |

**The default points at a service on the host, and a host firewall that drops
bridge-to-host traffic makes it unreachable from the containers.** `ufw` does
this by default on Arch and Ubuntu: `host.docker.internal` and the bridge
gateway (`172.17.0.1`) both time out from the worker, with no route error to
say why. `BLOCKCHAIN_RPC_URL` in `backend/.env.example` defaults the same way
(`http://host.docker.internal:8545`) and has the same problem.

Two remedies, either of which works for both: run the service **inside the
compose network** and point the variable at its service name, or open the
bridge to the host port (`ufw allow in on docker0 to any port 11434`). The
first is preferred, and it is what the local chain section below assumes.

**`LLM_EXTRA_HOSTS` is what makes the first remedy expressible, and it is
empty by default.** `_validate_local_base_url` admits `localhost`,
`127.0.0.1`, `::1` and `host.docker.internal` and nothing else until an
operator names a hostname in `LLM_EXTRA_HOSTS` — a comma-separated list, so
`LLM_EXTRA_HOSTS=ollama` with `LLM_BASE_URL=http://ollama:11434/v1` points
extraction at a sibling container. **The default is unchanged and the opt-in
is the whole control**: the allowlist is what makes *a document never leaves
this machine* true, and a compose service name is a weaker statement than a
loopback address, because `ollama` resolves to whatever is on that network.
Name only hosts you control, and only on a deployment where you know what
else is on the network. Entries are hostnames — no scheme, no port, no path —
because the value is compared against the URL's host and nothing else. **There
is no wildcard**: `LLM_EXTRA_HOSTS=*` admits a host literally named `*` and so
admits nothing, and `*.internal` likewise. There is no way to open this to a
range, which is deliberate — every admitted host is one an operator typed.

Installing the service on the host is **not sufficient on such a host**: an
operator who installs Ollama and sees the same failure has fixed the first
cause and not the second. Operator diagnostics name the settings to inspect —
`LLM_BASE_URL` and `LLM_MODEL` — and not their values,
because `_validate_local_base_url` checks the scheme, host, userinfo, query
and fragment and **never the path**, so a value like
`http://127.0.0.1:11434/v1/sk-proj-…` passes it and would otherwise reach the
uploader's screen. The member API derives its failure message from the extraction
status and never sends the stored diagnostic, including on historical attempts.
The operator can read that diagnostic in the extraction admin.

Connection failures, timeouts, rate limits and upstream server errors are retried
by the extraction task, up to three attempts spaced thirty seconds apart. SDK
retries are disabled so each recorded attempt makes one upstream request, and its
client connection is closed after the call. Invalid requests, model/configuration
errors and invalid extracted output stop after one attempt. Each attempt remains
in the extraction history. After correcting a terminal failure, the operator can
select its failed attempt in the extraction admin and re-run it. Unclassified
storage or rendering failures require that operator action; they are not assumed
to be transient.

### Clients

Client variables are public build configuration. They are embedded in the
bundle and must never hold a secret.

| File | Variables |
| --- | --- |
| `dashboard/.env` | `VITE_API_URL`, `VITE_LEDOVA_URL`, `VITE_MARKETING_URL`, `VITE_HOST`, `VITE_PORT`, `VITE_ALLOWED_HOSTS` |
| `marketing/.env` | `VITE_LEDOVA_URL`, `VITE_MARKETING_URL`, `VITE_HOST`, `VITE_PORT`, `VITE_ALLOWED_HOSTS` |
| `mobile/.env` | `EXPO_PUBLIC_API_URL`, `EXPO_PUBLIC_DEV_API_HOST`, `EXPO_PUBLIC_USE_MOCK_DATA`, `EXPO_PUBLIC_MARKETING_URL`, `EXPO_PUBLIC_SUPPORT_EMAIL`, `EXPO_PUBLIC_APP_STORE_URL` |

Mobile Release builds require HTTPS. Native Debug accepts loopback, the Android
emulator host, and one private LAN IPv4 explicitly selected with
`EXPO_PUBLIC_DEV_API_HOST` before prebuild. Set the API/marketing URLs to that
same address when using it; a native rebuild is required to change the allowance.
Bearer requests, including absolute download URLs, must remain on the configured
API origin. API servers must serve requests directly: native API/SSE redirects
are refused, including 307/308 responses. Provider WebView navigation remains
independent and disallows insecure mixed content. [Mobile build and security
guidance](MOBILE.md) describes native validation and storage behavior.

### Contracts

Hardhat loads nothing from a file: `contracts/hardhat.config.ts` and the deploy
scripts read `process.env` directly, and there is no dotenv loader in the
package. Export the values you need into the deploying shell.
`contracts/.env.example` is a checklist of the names, not a file Hardhat reads;
`scripts/init-local-env.py` does not create `contracts/.env` and nothing would
load it if you did. `DEPLOYER_PRIVATE_KEY` is a signing key: see
[Key management](#key-management).

| Variable | Used by |
| --- | --- |
| `DEPLOYER_PRIVATE_KEY` (secret) | the `localhost` and `baseSepolia` account lists; blank against `localhost` falls back to the node's own accounts, blank against `baseSepolia` leaves it with no signer |
| `BASE_SEPOLIA_RPC_URL`, `ETHERSCAN_API_KEY`, `REPORT_GAS` | network URL, contract verification, gas reporting |
| `FACTORY_ADDRESS`, `WHITELIST_ADDRESS`, `STABLECOIN_ADDRESS`, `SHARE_TOKEN_ADDRESS`, `RELAYER_ADDRESS`, `TOKEN_NAME`, `TOKEN_SYMBOL`, `COMPANY_IDENTIFIER`, `AUTHORIZED_SHARES`, `INITIAL_MINT` | inputs to the individual deploy scripts |

## Seeding

The compose `migrate` service runs, in order:

```
python manage.py migrate --noinput
python manage.py sync_monitoring_rules
python manage.py sync_procedure_templates
python manage.py asset_sync --seed-only
```

All three seed commands are idempotent and reconcile their tables to the seed
modules. `--seed-only` upserts the supported assets and their chain
deployments and touches no network. Running the backend outside Docker
(`make run` in `backend/`) means running all four by hand once.

Consequences of skipping them:

- Without `sync_monitoring_rules` and `sync_procedure_templates` no monitoring
  rule exists, so no compliance alert is ever raised.
- Without `asset_sync --seed-only` there are no verified rows for the supported
  native assets. Native transfer discovery can create the coin and its
  deployment, but does not verify or price the asset. The seed does not change the suffixed-symbol
  quarantine either way: `RESERVED_SYMBOLS` in `assets/services/identity.py` is
  a module constant built from `SUPPORTED_ASSETS`, so a token declaring a
  supported symbol is quarantined whether or not the seed ran.

The published monitoring seed
(`backend/compliance/seeds/monitoring_rules.py`, with `ALERT_THRESHOLD_AUD` in
`backend/compliance/constants.py`) carries the generic AUSTRAC-public figures,
AUD 10,000 being the statutory threshold-transaction amount. Operational
thresholds and evasion-sensitive rules belong outside this repository.

`asset_sync --seed-only` also writes the `AUDY` `AssetChainDeployment` on
`base` from `STABLECOIN_CONTRACT_ADDRESS`. An empty setting leaves any address
already recorded untouched.

Native coins have one asset row and a contract-less deployment on each supported
network: ETH on Ethereum and Base, BTC on Bitcoin. Migration `assets/0014`
adds missing deployments for existing native rows without changing holdings,
prices, wallet identity, or existing deployment settings. Reversing this data
migration preserves those deployments because they may already be in use.
Seeding preserves disabled deployments and existing native contract/decimal
settings. A native deployment with a contract address or incorrect decimals is
unavailable until an operator repairs its configuration. Transfer preparation
returns a service error for missing or unavailable native configuration instead
of reporting a zero balance. An operator-disabled coin stays unavailable.
Already-recorded transfers can still confirm, fail or be reversed using their
existing asset identity and debit records. Unavailable chain reads leave balance
reconciliation pending; they do not recreate a removed deployment.

### Valuation sources

Portfolio values and new asset snapshots use USD. Asset price writes record
`market` for provider/manual quotes, `nav` for NAV updates, or `par` for the
configured par reference. AUDY uses one AUD per token divided by the stored
USD/AUD exchange rate; seed-only does not create an FX quote. Sync exchange
rates before refreshing asset prices. Without a positive finite rate, a new
AUDY holding remains unpriced. A later provider outage preserves the last
valid cached quote, as it does for market prices; this is not live pricing.
Manual quotes in another currency also require a stored conversion rate.

Migration `assets/0013` preserves existing cached prices but leaves their
provenance unknown. Until a producer refresh or the admin **Update prices**
action records their source, the API returns a null current price and excludes
them from current valuations. Direct price, currency and source fields are
read-only in the admin. Historical snapshots remain unchanged; no FX history
or source is guessed for old records.

### Demo data

`python manage.py seed_demo` creates a browser-ready local demo in one run: the
operator row with payment rails, a superuser, a company owner who can sign in,
an `ACTIVE` company with a verified issuer wallet recorded as its
`operator_wallet` and a draft share class, and an investor with a verified
wallet, a live wholesale classification and a whitelist row. Without it,
reaching that state by hand means a signup, nine document uploads, a listing
submission, three admin transitions and a wallet verification. A typed EVM
address can be verified in the dashboard by signing the challenge with its seed
phrase; a Bitcoin address, or an EVM address whose key you do not hold, still
reaches `verified` only through a Keystone or the admin.

No password is stored in the repository. The command takes `--password`, falls
back to `$LEDOVA_DEMO_PASSWORD`, and otherwise generates one and prints it with
the rest of the credentials. Re-running applies whichever it resolves, so the
credentials it prints are always the ones that work.

**It is deliberately not in the compose `migrate` chain**, and it refuses to run
unless `DEBUG` is on. That chain runs wherever the stack is deployed, and this
command creates accounts with a known password; `--force` overrides the guard
for a throwaway database that runs with `DEBUG` off. It is idempotent — a second
run reports `0 created` — and it refuses rather than adopting a company whose
ACN it wants but whose owner is someone else.

It writes **nothing to any chain**. The share class stays a draft and the
whitelist row is a database row only: `WhitelistEntry` alone does not put an
address on the `WhitelistRegistry`, and the on-chain reads in
`share_token_service` and `transfer_service` ask the contract, not the table. So
a seeded investor is not actually whitelisted on chain — deploying the token and
minting to them are the deliberate next steps, and both write real transactions.
The wallet addresses are Hardhat accounts #0 and #1 rather than invented
strings, so the seeded data survives contact with a local node.

## Asset allowlist

Asset identity is `(chain, contract_address)` through `AssetChainDeployment`.
A contract the allowlist does not know is recorded as an unverified `Asset`
under a symbol no other row owns (the declared symbol, or the symbol plus a
growing hex prefix of the contract address), compared case-insensitively.

- Unverified rows are invisible to customers: the asset list and detail,
  snapshots, favourites, wallet holdings, transactions, market values, price
  sync and the portfolio value series all filter on `is_verified`. A quarantined
  row is never priced, and its transaction is kept for audit without opening a
  `Holding`.
- Allowlist a token with the asset admin's **Mark selected assets as verified
  (allowlist a quarantined token)** action.
- Switch a contract off by deactivating its chain deployment. Transfers for it
  are then skipped and logged, never booked.
- The same address on another chain is a different contract and gets its own
  unverified row. Add a second chain's deployment to a verified row by hand in
  the admin.

## Key management

- One key, `BLOCKCHAIN_OPERATOR_KEY`, owns the factory, the whitelist registry,
  the AtomicSwap contract and every share token, and signs every deployment,
  mint, cap change, whitelist write and pause. There is no key rotation path in
  the code: a new key means redeploying or transferring ownership of each
  contract.
- Keep it outside version control. `.env` files created by
  `scripts/init-local-env.py` are mode 0600 and gitignored.
- For local work use Hardhat account #0
  (`0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80`). It is
  a public development key and must never hold anything of value.
- `DEPLOYER_PRIVATE_KEY` is the key Hardhat signs the deployment with; it reads
  it from `process.env` into the `localhost` and `baseSepolia` account lists.
  Export it in the deploying shell for the length of the deployment; nothing
  loads it from a file. Leave it unset against `localhost`, where Hardhat falls
  back to the node's own accounts.
- **It is not a second, independent key.**
  `contracts/scripts/deploy-all.ts` passes `deployer.address` as the owner of
  WhitelistRegistry, ShareTokenFactory, AUDY and AtomicSwap, and it is also the
  address added as the AUDY minter. The backend signs every `onlyOwner` call
  with `BLOCKCHAIN_OPERATOR_KEY`. The two keys must therefore resolve to the
  **same address**, or ownership of all four contracts must be transferred to
  the `BLOCKCHAIN_OPERATOR_KEY` address after deployment. Deploy with one key
  and operate with another, without transferring ownership, and every mint, cap
  change, whitelist write and pause reverts.
- Client `.env` files hold no secrets by construction: `VITE_` and
  `EXPO_PUBLIC_` values are embedded in the shipped bundle.

## Chain configuration

`backend/ledova_backend/chain_safety.py` refuses any EVM chain id outside `{1337, 31337, 84532,
11155111}` and any Bitcoin network other than `test` or `regtest`, at startup.
The Hardhat deployment scripts refuse any chain id outside `{1337, 31337,
84532}`. Mainnet configuration is absent by design.

Local chain, in two terminals from the repository root:

```bash
cd contracts && npx hardhat node          # chain id 31337, port 8545
npm --prefix contracts run deploy:local:core
```

The deployment writes `WHITELIST_CONTRACT_ADDRESS`,
`SHARE_TOKEN_FACTORY_ADDRESS`, `ATOMIC_SWAP_ADDRESS` and
`STABLECOIN_CONTRACT_ADDRESS` to `.deployed-contracts.env`. Copy them into
`backend/.env` with `BLOCKCHAIN_RPC_URL`, `BLOCKCHAIN_CHAIN_ID=31337` and the
Hardhat account #0 key as `BLOCKCHAIN_OPERATOR_KEY`.

Share-token explorer links follow the chain the contract is actually on.
`ShareToken.chain` records it, written next to `contract_address` by
`mark_deployed()` when `ShareTokenService._finish_deployment` confirms the
factory receipt, so it is the chain the deployment path recorded and it cannot be
lost afterwards. `ShareTokenDetailSerializer` carries it read-only; the clients
render an explorer link only when both `chain` and `contractAddress` are set.

The address alone cannot supply the chain. `AssetChainDeployment` is unique on
`(chain, contract_address)`, so the same address may legitimately exist on
several chains — routine for CREATE2 and bridged tokens — and matching an
`AssetChainDeployment` by address would pick whichever row happened to be
created first, from any asset. Nor can the asset bridge supply it: every silent
return in `bridge_share_asset` leaves a confirmed deployment with no
`AssetChainDeployment` row at all. Migration `tokens.0017_share_token_chain`
backfills every existing token that has a contract address to `base`, the only
chain the factory has ever deployed to.

Base Sepolia (chain id 84532) is the supported public testnet:
`npm --prefix contracts run deploy:testnet`, with `DEPLOYER_PRIVATE_KEY` and
`BASE_SEPOLIA_RPC_URL` exported in that shell. The `DEPLOYER_PRIVATE_KEY`
address becomes the owner of all four contracts, so it must be the same signer
as the `BLOCKCHAIN_OPERATOR_KEY` you put in `backend/.env`, or you must transfer
ownership of WhitelistRegistry, ShareTokenFactory, AUDY and AtomicSwap to the
operator address immediately after deploying. Otherwise the backend's
`onlyOwner` calls revert against the freshly deployed contracts.

`make chain-test` does the local sequence unattended: it compiles, starts a
node, waits for `eth_chainId`, deploys the core contracts, sources
`.deployed-contracts.env` and runs
`backend/tokens/tests/test_chain_integration.py`, then stops the node.
`CHAIN_TEST_PORT` moves the whole thing — the node, the `localhost` network the
deploy connects to (through `LOCALHOST_RPC_URL`, which
`contracts/hardhat.config.ts` reads) and the backend's `BLOCKCHAIN_RPC_URL` — so
two worktrees can run the chain test at the same time on different ports. The
target refuses to start when that port is already taken, naming the port rather
than failing later with Hardhat's `HH108`.
`CHAIN_TEST_SETTINGS=ledova_backend.settings.test_postgres` (with the
`POSTGRES_*` variables set) runs it on PostgreSQL, which adds the two-worker
capital-increase case that needs real row locks. CI runs both.

Wallet ownership challenges expire five minutes after issuance, including the
exact five-minute boundary. Requesting another challenge replaces the nonce and
restarts that window; successful verification consumes it. The message and the
server use the same `WALLET_VERIFICATION_CHALLENGE_MINUTES` setting and stored
issue time. Migration `wallets/0011` adds that internal timestamp. Outstanding
challenges issued before the migration have no trustworthy issue time and must
be requested and signed again. Existing verified wallets keep their status.

Wallet identity is `(account, network, address)`. An account can register the
same EVM address on Ethereum and Base, each with its own UUID, verification,
holdings and transactions. EVM address case variants are the same identity
within that account and network; Bitcoin addresses retain their case.
Migration `wallets/0014` adds both database constraints and preserves existing
wallet UUIDs and financial references. It stops if old EVM records differ only
in address case within one account and network. Review those conflicting records
and their references before retrying; the migration does not merge or delete
them. Reversal also refuses if the old account/address constraint cannot
represent wallets registered on two networks.

Wallet and transaction address filters require an explicit `chain`. A
transaction query may instead supply a visible `wallet` UUID, from which the
network is derived. Queries without an address filter can still list multiple
networks. Chain filters accept the supported network names and aliases.

Share-token and whitelist operations use the application's Base registry
network; `receiving_wallet_chain` selects the payment network and does not
retarget that registry. Address-based registry identity, issuance holdings and
admin wallet selection therefore use Base wallets. Multiple accounts with the
same Base address remain ambiguous. A company needs its selected operator
wallet, or a verified owner wallet, on the requested network. Ethereum wallets
no longer stand in for Base wallets. Historical whitelist rows linked to another
network remain visible to operations for review and are excluded from registry
address resolution; their wallet ownership is not rewritten automatically.

Portfolio history keeps one holding entry per asset and adds `perChain` to
each entry in the API response. Each slice identifies its network, exact
decimal quantity and wallet UUIDs, plus `marketValue` when a historical price
exists. Two registrations of the same address on different networks stay in
their respective slices; the portfolio total still sums the asset once across
those slices. The price belongs to the canonical asset and applies to each
network's recorded quantity for that date.

The breakdown comes from daily `HoldingSnapshot` rows and their wallet links.
Quantities carry forward from the last recorded day, including a recorded zero;
current live balances do not replace historical quantities. There is no history
before the first recorded holding. Dashboard and mobile expose the split under
the chart's Holdings view, following the selected date. Older responses without
network detail offer no expansion. A missing price is shown as unpriced, while
a priced zero stays zero. Base transfers use ETH for native quantities and gas
fees, and use Base's chain ID for signing.

## Background jobs

Procrastinate runs on PostgreSQL. Start a worker with
`python manage.py procrastinate worker --queues=default,builtin` (the compose
`worker` service and `make worker` in `backend/`).
`ledova_backend/worker_entrypoint.py` is an alternative entrypoint that also
serves a health endpoint on `PORT` (default 8080) for platforms that require
one.

| Schedule | Task |
| --- | --- |
| every minute | `expire_unclaimed_matches` |
| every 5 min | `check_pending_token_deployments`, `check_executing_issuance_requests`, `offerings.reconcile_subscriptions`, `check_pending_transactions`, `check_all_pending_transactions` |
| every 10 min | `assets.sync_all_assets`, `assets.sync_exchange_rates` |
| every 30 min | whitelist `sync_all_entries` |
| hourly | `sync_all_wallets`, `compliance.tasks.run_batch_monitoring` |
| daily 03:00 | `cleanup_failed_transactions`, `cleanup_stale_pending_transactions`, `offerings.expire_unpaid_subscriptions`, `users.purge_classification_evidence` |
| daily 04:00 | `compliance.tasks.check_periodic_reviews` |

`expire_unclaimed_matches` releases the reserved share quantity of an expired
swap only when the current matching service marked it eligible at creation,
both orders still name that match, and no execution claim, transaction record,
hash or other active match exists. The sweep locks both orders in identifier
order, then the current swap, and commits each release separately. It preserves
previously filled quantities and signed terms, marks the swap `expired`, and
publishes `swap_expired` so both clients refresh their orders and swaps. A retry
cannot release the same reservation twice. Signing still stops at the recorded
deadline; the worker makes eligible orders available on its next minute sweep.
The order book and best prices include reopened partially filled orders using
only their remaining quantity.

`tokens/0036_swap_expiry_eligibility` leaves existing rows ineligible and prevents
changing the marker on PostgreSQL. Do not backfill it: missing transaction data
in a legacy row does not establish that nothing was sent. Deploy this code to
all API and worker processes and stop older processes before permitting new
matches; the eligibility marker describes the current service's durable claim
protocol. Claimed, executing, inconsistent and legacy matches retain their
reservations for reconciliation. This sweep does not inspect the chain, refund
money, cancel a broadcast or change an existing signature/deadline. Trading
remains disabled by default.

`reconcile_subscriptions` is the mirror of `check_executing_issuance_requests`
on the subscription row. The issuance sweep finishes a request a killed worker
left mid-execution; without the mirror the subscription that request belongs to
sits `paid` forever while the shares are already on chain. It flips a paid
subscription to allotted when its linked request reached `executed` and touches
nothing else. `expire_unpaid_subscriptions` only ever touches a subscription
that is awaiting payment, past its due date, and has no payment recorded
against it — a part-paid row is left for the operator.

Share issuances created after `tokens/0034` keep a private `mint_journal`.
Each attempt records its fixed transaction hash and signed payload in a durable
database transaction **before** submitting it to the node. The payload already
contains the account nonce and chain ID. Wrapping mint execution in another
database transaction is refused because a rollback after submission would lose
that identity. The journal is omitted from API responses and admin forms;
database backups containing it carry signed transactions that can be broadcast.

If a worker stops after signing, retrying the request or running
`check_executing_issuance_requests` looks for its receipt and, when no receipt
is available, resubmits the **same signed bytes**. A missing receipt or transaction
does not prove that submission never happened. Duplicate, nonce-too-low and
unavailable-provider responses leave the recorded transaction unresolved until
its receipt can be read; they never authorize a new nonce. A confirmed revert
permits a new signed attempt while preserving the previous attempt in the journal.
The global signer nonce coordination and receipt finality work remain separate
hardening items; trading remains disabled by default.

If the journal shows that an attempt stopped before recording any signed
transaction, the stale-execution sweep closes that attempt and releases the
request for retry. A delayed worker cannot subsequently submit that closed
attempt. Legacy rows have a null journal and cannot establish this fact: their
hashless state remains unresolved, including rows previously marked failed.
Those legacy rows also block subscription refunds until their mint is resolved;
an attempt whose journal proves it failed or was closed before signing remains
refundable.
Once the legacy grace period has passed, the admin offers **Record legacy
transaction hash** for those rows. Identify this request's mint in the operator's
transaction history and record its hash so the sweep can reconcile it. The old
**Release claim** action has been removed; provider absence alone is insufficient
evidence for issuing again. Legacy rows that already identify a transaction
continue receipt-based reconciliation and cannot replay without a saved payload.

`blockchain.services.outgoing` provides the durable outgoing transaction
foundation for the next signer migration. It has no production send callers yet;
existing transfer, deployment and mint paths keep their current behavior. Its
nonce coordination applies only to operations that use this service. Adopting
every signer path and importing or quarantining existing signed transactions are
required before claiming coordination across the application.

The foundation now requires explicit signer admission. Existing and new
`SigningAccount` rows start `closed`, and a missing row is also closed. A nonce
counter, successful legacy status or inventory capture never grants admission.
There is no activation command or admin edit surface; admitted synthetic test
fixtures establish a test precondition only. Production adapters remain outside
this foundation and keep their existing behavior, including mint recovery.

`close_signer_admission(chain_id=..., sender=...)` is an operator-only service
that closes an account and advances its admission generation. It preserves
claims, outcomes, counters and every signed payload. Missing accounts are created
closed. Closure blocks preparation RPC, new signing and exact-byte broadcast;
receipt reconciliation remains available. Preparation records the generation,
and signing checks it again under the operation and signer locks. A delayed
preparer cannot survive a close/reopen cycle. The maximum signed 64-bit generation
is reserved for closure, so an admitted account can always close; further
advancement at that maximum is refused without wrap or reset.

Broadcast admission takes a short operation-then-signer lock and commits before
RPC. A call that crossed this boundary before closure may still send and record
its result afterward. Closure is a drain barrier, not instant cancellation or
credential revocation. Already signed reservations and exact-byte recovery must
survive that interval.

Before a later adapter is activated, every old same-key process and signing tool
must drain and lose credential access. Recapture history after that drain, bind
trusted authorization and intent, and import reservations or quarantine unresolved
signers. Every remaining same-key writer must use the foundation or be disabled
without legacy fallback. Old binaries do not consult this admission guard.
Provider absence, terminal history or today's key and chain cannot establish
historical authorization or release a nonce. App-role handoff and each adapter's
durable transaction boundary still require proof. After signed activity, rollback
cannot restore legacy sending with that key. Admission and the staged inventory
do not establish a global nonce guarantee or resolve old business operations.

Callers provide a stable operation key and immutable intent: chain, sender,
target, value and calldata. Reusing a key with different terms is refused.
`prepare_operation` reads the endpoint, pending nonce, gas price and gas estimate
outside database transactions. `sign_operation` then locks the operation followed
by the chain-and-sender account, allocates a nonce from the greater of the observed
pending nonce and the durable counter, and signs locally without RPC. The signed
bytes, fixed hash, nonce reservation and operation pointer commit together before
`broadcast_operation` can submit anything. All service entry points refuse an
enclosing database transaction or disabled autocommit.

Signing an already prepared claim returns the winning attempt once another
worker has signed, provided the signer remains admitted at the same generation.
Restarting an unsigned failed attempt changes its claim identifier and fences out
delayed workers. Once signed, uncertainty never authorizes another nonce: retries
validate and broadcast the saved bytes, and missing receipts, provider errors,
already-known responses and nonce errors leave the operation unresolved. Receipt
updates require the same claim and hash. A recorded revert permits a new claim
and nonce while retaining the immutable earlier attempt. Here `confirmed` means
a successful receipt was observed; confirmation depth, replacement detection and
reorg repair remain part of the separate finality work.

This initial API signs EIP-155 legacy gas-price transactions, including contract
creation. Chain IDs and gas limits fit a positive signed 64-bit database integer;
allocated nonces stop one below its maximum so the next counter still fits.
Transaction value and gas price accept unsigned 256-bit values. PostgreSQL
enforces immutable attempts, monotonic signer counters and guarded operation
transitions. All three tables deny application-role access, even with a user
principal; operator access is required. They have no admin or serializer surface.
Signed payloads are broadcast capabilities and belong in protected backups;
errors retain a category rather than provider or database exception text.

`inventory_outgoing_history` observes legacy operator history before the later
signer cutover. Run it from `backend/` with the operator management connection:

```bash
python manage.py inventory_outgoing_history
OUTGOING_CAPTURE_ID=$(python -c 'import uuid; print(uuid.uuid4())')
python manage.py inventory_outgoing_history --record --capture-id "$OUTGOING_CAPTURE_ID"
```

The first command only reads. Recording stages a private capture, every evidence
variant and append-only cutover holds together. Both modes operate locally;
neither signs, contacts a provider, broadcasts, reserves or releases a nonce,
changes the outgoing foundation, or edits a mint journal or legacy status.
Services refuse an application connection, any enclosing transaction and manual
autocommit disablement, including the originating connection before the command's
operator handoff. There is no activation or hold-resolution option.

The fixed inventory includes all share issuance journal slots, unlinked share
requests and operator transaction types in every status, plus mint, NAV, deployment, capital increase,
swap and whitelist source rows. Failed, reverted, completed, draft, hash-only and
hashless observations are retained. Stored transaction addresses and nonces are
claims until raw bytes establish them. Missing source links and unrecognized
payloads remain unresolved; conflicting payloads never replace one another.
Historical stablecoin burn records remain included after removal of the unused
Python burn helper.

For saved #303 mint bytes, local validation records signature/envelope validity,
the observed hash, chain, sender and nonce, exact target/value/mint calldata, and
matching request linkage separately. These checks do not establish historical
authorization. `ShareToken.chain` records a chain family such as `base`; the mint
journal has neither an independently expected historical numeric chain ID nor an
authorized signer. Today's chain configuration and key cannot supply that
history. Matching raw bytes, terms and source links therefore still carry
`missing_chain_provenance` and `missing_signer_authorization` holds. Legacy admin
hash naming continues to rely on the operator's verification; this inventory
does not replace that recovery path or validate a hash without its raw payload.

PostgreSQL collection uses one read-only repeatable-read snapshot. It closes
before local analysis and a separate durable staging transaction. A dedicated
transaction advisory lock serializes capture-ID checks, cross-capture conflict
analysis and insertion under read committed isolation. This lock coordinates
inventory writers; active signers can still advance independently. SQLite also
commits the batch atomically; a competing writer may need to retry after a busy
database refusal. The capture manifest excludes the capture clock and query
order. Re-entering the same ID with unchanged source returns the original batch;
changed selected source content, including source update timestamps, requires a
new ID. A later capture can retain new variants and append holds, but cannot
rewrite an earlier observation or clear its holds.

Reports contain counts and fixed reason codes, and always report
`cutover_authorized: false`. Private raw payloads and source snapshots have no
admin, serializer or application-role access. PostgreSQL denies even operator
UPDATE/DELETE of all three inventory tables; keep them in protected backups.
Malformed raw text is retained privately, and command errors omit database
exception text.

An inventory is a point-in-time observation to revalidate after old signers
drain. Historical pause/approval sends and offline or old CLI/binary key use are
not fully observable in these tables. Unknown historical signer identity stays
unassigned and can require a deployment-wide hold. Neither an empty mempool nor
an unchanged-looking snapshot authorizes cutover. Later adoption must drain all
old signing paths, revalidate provenance and coverage, then perform a separate
guarded import/activation. Application requests will also need scoped
authorization before a narrow operator handoff, with transaction-boundary checks
on the originating connection. Those adapter changes remain future work, and
trading stays disabled.

`purge_classification_evidence` deletes the evidence file of an investor
classification once it is past its retention horizon, leaving the row, its
status and its review outcome untouched. There is one horizon and two things
enforce it, deliberately: the four serving paths — the API evidence route, the
admin evidence view, the admin link and the serializer's `evidenceUrl` — all
refuse past it, so a claim stops being readable the moment it crosses, without
waiting up to twenty-four hours for the sweep and without depending on the
worker being alive; and the sweep then actually deletes the bytes, because
deletion is a side effect and cannot be derived the way `expires_at` is. No
status column records the purge: a cleared `evidence_file` is the record, which
is the same choice `expires_at` makes in not storing an expired status. The
clock is `reviewed_at` for a rejected or revoked claim and `expires_at` for one
that expired; a claim with no clock stamped is never swept. `evidence_file_size`
and `evidence_mime_type` survive, being content-free metadata rather than the
document. See `CLASSIFICATION_EVIDENCE_RETENTION_DAYS` above; `0` retains
indefinitely.

Deleting an account does **not** purge evidence early. `delete_account` is a
tombstone that never touches `InvestorClassification`, and that is now a
deliberate position rather than an oversight: the point of a fixed retention
period is that it outlives the subject's wishes, which is usually why the
record-keeping obligation exists. The period itself is the part that needs
counsel.

`GET /health/` is answered by middleware before any database access.

### Supporting payslips

Migration `documents/0003` preserves existing uploads as unattached documents
and creates an empty **Document operations** group with document, extraction
and classification view permissions. Assign the group only to the platform
staff who need to review this evidence. It grants no classification verification
or editing permission and assigns no users automatically. Staff must be active;
company owners and accounts with a company role cannot use the cross-customer
document review paths, even if granted a document permission. Registry platform
superusers retain the same read access; single-issuer mode disables it.

On Profile, an investor can choose an existing submitted classification claim
when uploading a payslip, or attach an existing unattached payslip afterward.
Attachment is final and is refused once a human has reviewed or the investor
has withdrawn the claim. The claim's admin page links the retained supporting
payslips for permitted reviewers. The document page links its original file
and extraction history, including the raw output. Extraction is material for a
human to check; it neither verifies the claim nor replaces its required evidence.

Every operations read of a document page, file, extraction page or corresponding
changelist writes a `DocumentRead` with reader ID, document and claim UUIDs, read
kind and time. A failed audit write prevents delivery. These records omit file
names and extracted figures, remain after content purge, and are read-only in
admin; reading the audit itself additionally requires `view_documentread`.

`purge_document_evidence` runs daily at 03:15 UTC in batches of 200. Attached
payslips use the claim's `evidence_horizon`: `reviewed_at` for rejected, revoked
or withdrawn claims, and `expires_at` for verified claims. Submitted claims and
claims without a clock retain their supporting evidence. The task deletes the
file and every extraction, including `raw_output`, and clears filenames and
notes while retaining the claim link and read audit. Storage failures retain the
reference for a later retry. File and extraction serving stop at the horizon
without waiting for the sweep, and a late extraction cannot recreate purged
content. Unattached documents retain the ordinary user-delete and orphan-file
cleanup behavior. Attached files live under `users/supporting-documents/`, and
neither row cascades nor the generic orphan sweep can delete them early.

## Notifications and push

Transaction confirmed and failed events, the KYC review outcome and every
company application transition defer
`users.tasks.notifications.send_push_notification`, which is what writes the
`Notification` row (`users/tasks/notifications.py`). A company transition
records nothing at transition time: `companies/services/company.py` only defers
the job. The in-app inbox (the dashboard bell, the mobile inbox) therefore needs
a running Procrastinate worker — with no worker the transition succeeds and the
inbox stays empty until one drains the queue.

Company transitions notify the owner as: submit, resubmit, start_review,
request_info (carrying the reason), approve, reject (carrying the reason),
activate and withdraw. Warning, resolve-warning, suspend, reinstate and delist
notify nobody. Only the Issue Warning action says so in its admin copy
(`companies/admin/company.py`); resolve-warning and reinstate have no intro copy
at all.

Delivery to a phone additionally needs `extra.eas.projectId` in
`mobile/app.json` plus a development or production build. It is not set in this
repository, and Expo Go cannot receive remote push on SDK 54. The inbox works
without it.

## Row-level security roles

`shared/0003_rls_roles_and_grants` creates `ledova_app` and `ledova_operator`,
grants them what they need, and `shared/0004_rls_policies` installs the helpers
and a policy on every tenant table. Four things about running that deployment:

- **Provision the roles and their credentials out of band**, and point the
  aliases at them with `RLS_APP_DB_USER`, `RLS_APP_DB_PASSWORD`,
  `RLS_OPERATOR_DB_USER` and `RLS_OPERATOR_DB_PASSWORD`. The migration creates
  the two roles if they are absent, so that development and CI have real ones
  rather than a mechanism that is inert exactly where it is tested — but it
  creates them **with no password**, and it never sets one. A credential does
  not belong in a migration: the statement carrying it reaches the server log on
  any instance with `log_statement = all`, and the migration is replayed on every
  database the schema is applied to. Local work uses
  `POSTGRES_HOST_AUTH_METHOD=trust`, which `docker-compose.yml` sets on the
  `postgres` service, as CI does on its service container.
- **`POSTGRES_HOST_AUTH_METHOD` is read by `initdb`, on the first start only.**
  Setting it against a database that already exists does nothing: `pg_hba.conf`
  was written when the volume was created. A cluster initialised without it
  authenticates `scram-sha-256` for anything but loopback — and the compose
  bridge is not loopback, so the two passwordless roles are refused there while
  `psql` from inside the container succeeds on the `127.0.0.1/32 trust` line
  and proves nothing. On an existing volume, give the roles the password the
  settings already expect rather than recreating the database:

  ```sql
  ALTER ROLE ledova_app      LOGIN PASSWORD '<the POSTGRES_PASSWORD in backend/.env>';
  ALTER ROLE ledova_operator LOGIN PASSWORD '<the POSTGRES_PASSWORD in backend/.env>';
  ```

  `DATABASES["app"]["PASSWORD"]` falls back to `POSTGRES_PASSWORD` when
  `RLS_APP_DB_PASSWORD` is unset, so that is the value the connection sends.
  `manage.py check_rls_roles` says all of this when a connection is refused,
  rather than letting the failure surface as an authentication error inside
  whichever command happens to touch the ORM first.
- **`ALTER ROLE … BYPASSRLS` requires superuser.** Whoever applies
  `shared/0003` must be able to grant it, or the roles come out without the
  attributes the policies assume — which `check_rls_roles` then refuses.
- **Transaction-level connection pooling is incompatible, not discouraged.** The
  principal is a session-level `SET`, and a pgbouncer transaction-pooled handover
  does not carry it. The symptom is not an error: it is one request reading
  another user's principal. Session pooling or none.
- **`manage.py --settings=x runserver` refuses to boot**, and the message names the
  variable rather than the argument order. The runserver exemption is keyed on
  `sys.argv[1:2]`, so a global option before the subcommand makes `manage.py`
  set the operator ambient alias and the server's own guard then refuses to
  serve requests unscoped. That is the right side to fail on — it will not start
  rather than start wrong — but the error says `RLS_AMBIENT_ALIAS is
  'operator'`, which reads like a configuration problem. Put the subcommand
  first: `manage.py runserver --settings=x`.
- **`manage.py check_rls_roles` runs in CI's PostgreSQL step and in the compose
  `migrate` service, immediately after `migrate` and before the first command
  that touches the ORM.** That order is deliberate: a role the policies assume
  but the server will not admit is a role problem, and it should be reported
  by the command whose subject is the roles, not by `sync_monitoring_rules`.
  It
  connects on each alias and asserts what no test can see — the app role lacks
  `BYPASSRLS` and owns no table, the operator role has it, the migrate role owns
  the tables, and a fresh app connection carries no principal. A misconfigured
  `DATABASES["app"]` — the right role name against the wrong `USER` — passes the
  whole test suite and fails here, which is the only place the answer means
  anything.
- **CI's schema-generation step runs as the migrate role.** Generating the
  OpenAPI schema evaluates the views' querysets against the real `ledova`
  database, so the step that migrates and the step that generates must both hold
  a role that can read the schema. A step on the app role fails in a way that
  reads like a schema bug rather than a permissions one.

## Migration notes

- Every migration named below is reversible with `migrate`.
- `companies/0003_delete_review_and_signature_models` (with
  `tokens/0013_remove_transferorder_signature_request` before it) drops
  `ApplicationReview`, `ReviewNote` and `SignatureRequest`. **This is the one
  irreversible step in the release.** All three operations are `DeleteModel`,
  and reversing a `DeleteModel` recreates the table empty: rolling the migration
  back restores the schema and none of the rows. Export anything in
  `companies_applicationreview`, `companies_reviewnote` and
  `companies_signaturerequest` worth keeping before applying it.
- `portfolios/0004_delete_assetallocation`,
  `compliance/0005_remove_fiat_transaction_and_high_risk_country`,
  `wallets/0006_delete_fiattransaction_drop_unread_columns` (depends on
  `compliance/0005`) and `users/0017_delete_waitlist` drop the
  `asset_allocations`, `fiat_transactions` and `accounts_waitlist` tables and
  ten columns. Export any `accounts_waitlist` rows worth keeping first.
- `portfolios/0005_delete_portfoliosnapshot` drops `portfolio_snapshots`. The
  value series is computed on read in `portfolios/services/value_series.py`, and
  `GET /api/portfolios/{uuid}/snapshots/` keeps its path, parameters and row
  shape. The hourly `sync_all_wallets` job upserts one `DAILY` `HoldingSnapshot`
  per holding per day, so a wallet with no transactions still gets a point, and
  the series starts at a wallet's first holding snapshot rather than inventing
  anything before it. The nightly `sync_all_portfolios` periodic job no longer
  exists: delete any queued Procrastinate jobs under that name.
- `companies/0004_company_additional_info_response` stores the applicant's
  answer to a request for more information.
- `tokens/0035_trading_state_invariants` checks existing order/swap amounts,
  status/type values and the two challenge-consumption fields before installing
  constraints. Invalid data aborts the migration without changing any row; the
  error lists up to 20 UUIDs per violated rule. Resolve the identified history
  explicitly before retrying. Do not clamp fills, rewrite signed intent, reset
  consumed challenges or release unresolved swaps to make the migration pass.
  PostgreSQL then freezes each issued challenge's envelope and completed spend.
  Expired unspent challenges can still be purged. Existing unresolved swaps,
  including those without a transaction/hash, retain their state and quantities;
  neither timeout metadata nor nonce use alone resolves them. The current swap
  transaction UUID prevents competing preparation but does not provide signed
  transaction recovery after a process dies; #6 remains separate.
- `whitelist/0002_whitelistentry_treasury_addresses` makes
  `WhitelistEntry.wallet` nullable and adds `address` and `label` with a check
  constraint; `whitelist/0003` adds the partial unique constraint on `address`
  where `wallet` is null.
- `assets/0012_audy_base_deployment`, `tokens/0014_settlement_asset_columns`,
  `tokens/0015_fold_stablecoin_into_asset` and `tokens/0016_drop_stablecoin`
  fold `tokens.Stablecoin` into `assets.Asset`. Apply them in that order.
  `0014` also makes `SwapOrder.payment_token` nullable, which is what lets
  `0016` be unapplied on a database that holds swap orders; `0015` reverses by
  rebuilding a `Stablecoin` row for every asset it folded and every asset an
  order still points at, from that asset's deployment on
  `receiving_wallet_chain`, and re-pointing all three foreign keys, so
  `migrate tokens 0013_remove_transferorder_signature_request` returns the
  previous release's schema with the order history intact. `reserve_amount`,
  `reserve_updated_at` and the original `Stablecoin` uuids are not restored.
- The assets side of the fold is not undone at all. After a full rollback the
  database still holds every `assets.Asset` row `0015` created for a stablecoin
  that had no asset, every `assets.AssetChainDeployment` row it created on the
  settlement chain, and the contract address it wrote onto a deployment that
  already existed. `assets/0012` is separate and reverses on its own; nothing
  else on the assets side does. Drop those rows by hand if the rollback is
  meant to leave no trace, and remember they are what a re-applied `0015`
  matches against.
- `tokens/0015` refuses to run when a `Stablecoin` address disagrees with the
  address the matching asset already carries on the settlement chain. The
  migration is atomic, so the refusal writes nothing and names every
  conflicting pair: run `python manage.py migrate --noinput` against a restored
  copy of production to find out whether it fires, and reconcile the addresses
  before the real run. Overwriting the deployment silently would point mint,
  swap and transfer at a contract the stablecoin row does not name.
- `tokens/0015` also adds every folded asset, and `issued_stablecoin`, to
  `Operator.supported_settlement_assets`. Before the fold the settlement paths
  accepted any active `Stablecoin` with an address; after it they accept only
  what that many-to-many lists, so without the seeding
  `POST /api/v1/trading/transfer/prepare` would start refusing settlement
  assets and the wallet balance endpoint would stop listing them. Confirm the
  list in the operator admin after deploying. `0015` records the ids it
  actually added in a `tokens_stablecoin_fold_grant` table and its reverse
  removes only those, then drops the table, so an asset an operator had already
  configured by hand keeps its place through a rollback. A rollback run against
  a database folded by a build that predates that table logs a warning and
  leaves the many-to-many untouched.
- `assets/0012` moves the `AUDY` deployment from `ethereum` to `base` and gives
  it `STABLECOIN_CONTRACT_ADDRESS`. Any `AUDY` `Holding` keyed to the ethereum
  deployment stops resolving until the wallet sync runs again: count them
  before applying, and run `sync_all_wallets` (or wait one hour) after.

## Deploy checklist

1. `git status --porcelain` clean, CI green on the commit being deployed.
2. `make build` and `make check` pass; `make test` and `make chain-test` pass.
3. `.env` complete for the target: `SECRET_KEY`, the `POSTGRES_*` set,
   `DJANGO_ALLOWED_HOSTS`, `DJANGO_CORS_ALLOWED_ORIGINS` and
   `DJANGO_CSRF_TRUSTED_ORIGINS` listing the dashboard origin. `REDIS_URL` is
   needed only if the trading flag is ever turned on.
4. `DEBUG=false`, and therefore `COOKIE_SECURE` on and a real
   `SENDGRID_API_KEY` configured, or no email leaves the system.
5. Chain variables set and pointing at the intended testnet: RPC URL, chain id,
   operator key, and the four contract addresses.
6. `python manage.py migrate --noinput`, then `sync_monitoring_rules`,
   `sync_procedure_templates` and `asset_sync --seed-only`. On the settlement
   fold release, read Migration notes first: dry-run the migration against a
   restored copy, and queue `sync_all_wallets` afterwards.
7. **If the database predates the upload allowlist**, run the stored mime
   types over the three surfaces that serve a file inline, and read the answer
   before serving any of it with this code:

   ```sql
   SELECT 'documents' AS source, mime_type, COUNT(*) AS rows,
          MIN(created_at) AS first_seen, MAX(created_at) AS last_seen
   FROM documents GROUP BY mime_type
   UNION ALL
   SELECT 'companies_companydocument', mime_type, COUNT(*),
          MIN(created_at), MAX(created_at)
   FROM companies_companydocument GROUP BY mime_type
   UNION ALL
   SELECT 'users_investorclassification', evidence_mime_type, COUNT(*),
          MIN(created_at), MAX(created_at)
   FROM users_investorclassification GROUP BY evidence_mime_type
   ORDER BY source, rows DESC;
   ```

   **The expected answer is only `application/pdf`, `image/png` and
   `image/jpeg`** — `ALLOWED_UPLOAD_MIME_TYPES` in `shared/uploads.py`, which
   every one of the three write paths goes through. Anything else is a row the
   current validation could not have produced.

   The empty string counts as an answer. `Document.mime_type` and
   `evidence_mime_type` are `blank=True`, so `''` is a legal stored value;
   `CompanyDocument.mime_type` is not, so an empty string there is a different
   kind of surprise. It is what the blank row looks like — this is a local
   development database, and every row in it was written through the
   allowlist:

   ```
   source                       | mime_type       | rows
   companies_companydocument    | application/pdf |    9
   documents                    | application/pdf |    4
   users_investorclassification |                 |    1
   users_investorclassification | application/pdf |    1
   ```

   **`MIN`/`MAX(created_at)` is the part that answers the question.** If the
   out-of-allowlist values stop at a date, they are rows from before the
   validation and a one-off normalisation clears them. If they run to today,
   something is still writing them and that write path is what needs finding,
   before anything else.

   **A foreign row is already served as an attachment and never inline**, so
   this check is about the write path rather than the read: `stream_stored_file`
   sets `as_attachment` for any content type outside `INLINE_MIME_TYPES`, and an
   empty type falls back to `application/octet-stream`, which is outside it too.
   Do not relax that for a legacy row; normalise the row instead.

   **There is no production database today.** Every database the project has
   run against is local, and mainnet deployment configuration is deliberately
   absent from this repository. This step exists for the first deployment that
   restores or carries data written before the allowlist.
8. Open `/admin/operators/operator/` and complete identity, deployment mode and
   payment rails before inviting anyone; the console's health strip must be all
   green before an offering opens. Enter the changelist, not
   `/admin/operators/operator/1/change/`: only `OperatorAdmin.changelist_view`
   seeds the row, so on a fresh install the change URL redirects to `/admin/`.
9. Confirm a worker is running; check the deployment, issuance and confirmation
   sweeps appear in its log.
10. Confirm `GET /health/` answers 200 and `GET /api/operator/` returns 401
   anonymously.
11. Leave the `trading_enabled` feature flag off; while it is off the
    middleware refuses with 403 any request, of any method, whose path starts
    with one of five prefixes
    (`/api/v1/trading/{orders,wallets,transfers,swaps,events}/`). The read-only
    market route (`tokens/`) and the whitelist status route sit
    outside the gate by design. Enabling the flag does not make the trading
    implementation safe.

## Pre-release device checks

Three flows cannot be exercised in CI or a simulator and need real hardware
before any release. The first needs a Keystone; the rest need a development or
production build on a device:

- **The Keystone QR round trip.** Nothing in CI scans a QR code, so the whole
  air-gapped path — UR encoding, the animated fragments, the camera decoder and
  the device's own firmware — is covered by this check alone. Verify a wallet,
  send one EVM crypto transfer through the transfer signing flow, and sign one
  trading order through the QR branch. The transfer is the only place a raw
  transaction UR is exercised at all, and the encoder force-encodes a legacy
  type-0 transaction, so an EIP-1559 prepare is downgraded on the way to the
  device: check that what the Keystone displays matches what was prepared. The
  seed-phrase alternative in the dashboard does not cover any of this.

- **Bitcoin manual send.** Prepare a transfer from a Bitcoin wallet, sign the
  raw transaction with your own tooling, paste the hex, broadcast it, and
  confirm the success state links to the testnet explorer. The app never builds
  or signs a Bitcoin transaction.
- **Biometric sign-in.** Enable it, sign out, sign back in with biometrics,
  then rotate the session and confirm the gated copy of the refresh token stays
  in step. Android's Keystore prompts on every gated write and drops the copy
  when the prompt is cancelled or the app is backgrounded, so the next sign-in
  is typed once; iOS writes silently.

Push delivery is the third: it needs `extra.eas.projectId` and a real build, as
above.

## Legal

The operator's obligations under securities, AML/CTF, privacy and company-law
regimes are out of scope for this repository and must be settled with counsel
before any real issuance.


### Wallet signing preference migration

`wallets/0013` renames `wallet_type` to `signing_preference` and preserves each
recorded value. New unspecified wallets default to null. The field and imported
key metadata are self-declared hints; operators must not use either as custody
assurance. The API continues to accept and return `walletType` as a legacy alias,
while current clients use `signingPreference`. Supplying different values under
both names is a validation error. A matching address signature does not attest
which device held the key, and changing this preference does not verify an
address or remove an existing verification.

Apply the backend migration and release its API before updating the clients.
Older clients continue to use the legacy alias with the updated backend; the
new clients require an API that serves `signingPreference`.
