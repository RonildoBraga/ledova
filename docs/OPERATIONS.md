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
  address, which only the operator can resolve, since
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
them yet, and `deployment_mode` does not change any isolation rule.

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
| `REDIS_URL` | `redis://redis:6379/0` | **Yes.** It is `CACHES["default"]`, which holds the sign-in throttle, and it is the trading event stream (`tokens/events.py`, `tokens/views/trading_events.py`). Background work is still Procrastinate on PostgreSQL |

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
the strict atomic rolling window applies to `auth_email`.

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
`REDIS_URL` in that file is silently ignored inside the local stack. `DEBUG` is
forced alongside the storage backend because local storage is only servable
while `DEBUG` is true — see Media storage — so the pair is set together rather
than left half in a file this compose file declares optional.

`backend/.env` is still needed: `SECRET_KEY` and `POSTGRES_PASSWORD` come only
from it, and no committed file can supply them. Without it `postgres` refuses to
initialise and `migrate` dies on `KeyError: 'SECRET_KEY'` before anything
reaches the media guard. Run `make init-local` first; `make dev-up` checks.

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
| `SWAP_ORDER_EXPIRY_HOURS` | `24` | No |

### Data retention

| Variable | Default | Required |
| --- | --- | --- |
| `CLASSIFICATION_EVIDENCE_RETENTION_DAYS` | `2557` | No; `0` retains indefinitely and purges nothing |

Days an investor classification's evidence file is kept after the claim is
rejected, revoked or expires. The default is a **placeholder pending counsel,
not advice**: 2557 days is seven calendar years including two leap days.
Australian financial-record and AML/CTF customer-identification obligations are
the constraints to confirm it against. Set `0` while the period is undecided —
serving and purging both stop, and nothing is deleted.

### Media storage

| Variable | Default | Required |
| --- | --- | --- |
| `STORAGE_BACKEND` | `local` | No; `local`, `s3` or `gcs`, and forced to `local` whenever `DEBUG` is on |
| `AWS_STORAGE_BUCKET_NAME` | none | Yes when `STORAGE_BACKEND=s3` |
| `AWS_S3_REGION_NAME` | `ap-southeast-2` | No |
| `GS_BUCKET_NAME` | none | Yes when `STORAGE_BACKEND=gcs` |

S3 and GCS objects are served through signed URLs that expire after 300
seconds, with `file_overwrite` off.

`local` is a development-only backend. The `/media/` route exists only while
`DEBUG` is on (`ledova_backend/urls.py` builds it with
`django.conf.urls.static.static()`, which returns no patterns otherwise) and
WhiteNoise is configured for `STATIC_ROOT` only, so with `DEBUG=false` every
uploaded document answers 404. `ledova_backend/wsgi.py` and
`ledova_backend/asgi.py` therefore raise `ImproperlyConfigured` at startup when
`DEBUG` is false and the resolved backend is `local`: choose `s3` or `gcs` for
any deployment.

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

Manual wallet sync returns `success: false` with an actionable `syncResult.error`
when verification is missing, the provider fails, history cannot be read or a
known holding cannot be refreshed. Both clients display that reason. A partial
refresh keeps any balances it did read, and leaves the wallet's last successful
sync time unchanged.

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
| `mobile/.env` | `EXPO_PUBLIC_API_URL`, `EXPO_PUBLIC_USE_MOCK_DATA`, `EXPO_PUBLIC_MARKETING_URL`, `EXPO_PUBLIC_SUPPORT_EMAIL`, `EXPO_PUBLIC_APP_STORE_URL` |

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
  native assets and no `AssetChainDeployment` for them, so chain sync has
  nothing to attach balances to. The seed does not change the suffixed-symbol
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

### Demo data

`python manage.py seed_demo` creates a browser-ready local demo in one run: the
operator row with payment rails, a superuser, a company owner who can sign in,
an `ACTIVE` company with a verified issuer wallet recorded as its
`operator_wallet` and a draft share class, and an investor with a verified
wallet, a live wholesale classification and a whitelist row. Without it,
reaching that state by hand means a signup, nine document uploads, a listing
submission, three admin transitions and a wallet the dashboard cannot verify —
the Verify flow is hardware-wallet only, so a typed address only reaches
`verified` through the admin.

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

## Background jobs

Procrastinate runs on PostgreSQL. Start a worker with
`python manage.py procrastinate worker --queues=default,builtin` (the compose
`worker` service and `make worker` in `backend/`).
`ledova_backend/worker_entrypoint.py` is an alternative entrypoint that also
serves a health endpoint on `PORT` (default 8080) for platforms that require
one.

| Schedule | Task |
| --- | --- |
| every 5 min | `check_pending_token_deployments`, `check_executing_issuance_requests`, `offerings.reconcile_subscriptions`, `check_pending_transactions`, `check_all_pending_transactions` |
| every 10 min | `assets.sync_all_assets`, `assets.sync_exchange_rates` |
| every 30 min | whitelist `sync_all_entries` |
| hourly | `sync_all_wallets`, `compliance.tasks.run_batch_monitoring` |
| daily 03:00 | `cleanup_failed_transactions`, `cleanup_stale_pending_transactions`, `offerings.expire_unpaid_subscriptions`, `users.purge_classification_evidence` |
| daily 04:00 | `compliance.tasks.check_periodic_reviews` |

`reconcile_subscriptions` is the mirror of `check_executing_issuance_requests`
on the subscription row. The issuance sweep finishes a request a killed worker
left mid-execution; without the mirror the subscription that request belongs to
sits `paid` forever while the shares are already on chain. It flips a paid
subscription to allotted when its linked request reached `executed` and touches
nothing else. `expire_unpaid_subscriptions` only ever touches a subscription
that is awaiting payment, past its due date, and has no payment recorded
against it — a part-paid row is left for the operator.

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

Two mobile flows cannot be exercised in CI or a simulator and need a real
development or production build on a device before any release:

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
