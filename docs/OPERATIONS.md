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
  missing and redirects to the single change page,
  `/admin/operators/operator/1/change/`. Always enter through the changelist:
  the change URL alone redirects to `/admin/` on a fresh install, because
  `changelist_view` is the only thing that creates the row. Add is offered only
  while no row exists; delete never is. One row is enforced three ways: a fixed primary key
  of 1, a `CheckConstraint` on it, and a guard in `save()`.
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
rows of type `stablecoin`.

`GET /api/operator/` (authenticated; 401 for anonymous) returns `name`,
`legalName`, `abn`, `contactEmail`, `website`, `deploymentMode`,
`supportedSettlementAssets`, `issuedStablecoin`, `investorKycRequired`,
`issuerKycRequired` and `paymentInstructions`, which carries only the payment
fields that are set (and the chain only when the wallet address is set).

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
| `REDIS_URL` | `redis://redis:6379/0` | Only for the trading event stream (`tokens/events.py`, `tokens/views/trading_events.py`), which is off while the trading flag is off. Nothing else reads it: background work is Procrastinate on PostgreSQL and there is no `CACHES` setting |

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
`redis://redis:6379/0` and `STORAGE_BACKEND` to `local` for the `migrate`,
`backend` and `worker` services. These are `environment:` entries, so they win
over `backend/.env`: a `STORAGE_BACKEND=s3` or a custom `REDIS_URL` in that file
is silently ignored inside the local stack. Because the stack forces local
storage, `backend/.env` must keep `DEBUG=true` (as `.env.example` does) or the
ASGI entrypoint refuses to start — see Media storage.

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
| `STABLECOIN_CONTRACT_ADDRESS` | empty | Only for stablecoin payment |
| `SWAP_ORDER_EXPIRY_HOURS` | `24` | No |

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

`python manage.py sync_contracts` writes the `AUDY` `Stablecoin` row from
`STABLECOIN_CONTRACT_ADDRESS` (or `--stablecoin-address`). It is not part of
the compose chain.

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

Share-token explorer links in both clients are hardcoded to Base:
`dashboard/src/pages/company/index.tsx` and
`mobile/src/screens/company-tokens/TokenDetailScreen.tsx` each set
`const TOKEN_CHAIN = BLOCKCHAIN.BASE` because the share-token serializer carries
no chain field. Deploy share tokens anywhere else and those links point at the
wrong explorer.

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
`CHAIN_TEST_PORT` moves the node.
`CHAIN_TEST_SETTINGS=ledova_backend.settings.test_postgres` (with the
`POSTGRES_*` variables set) runs it on PostgreSQL, which adds the two-worker
capital-increase case that needs real row locks. CI runs both.

## Background jobs

Procrastinate runs on PostgreSQL. Start a worker with
`python manage.py procrastinate worker --queues=default,builtin` (the compose
`worker` service and `make worker` in `backend/`).
`ledova_backend/worker_entrypoint.py` is an alternative entrypoint that also
serves a health endpoint on `PORT` (default 8080) for platforms that require
one.

| Schedule | Task |
| --- | --- |
| every 5 min | `check_pending_token_deployments`, `check_executing_issuance_requests`, `check_pending_transactions`, `check_all_pending_transactions` |
| every 10 min | `assets.sync_all_assets`, `assets.sync_exchange_rates` |
| every 30 min | whitelist `sync_all_entries` |
| hourly | `sync_all_wallets`, `compliance.tasks.run_batch_monitoring` |
| daily 03:00 | `cleanup_failed_transactions`, `cleanup_stale_pending_transactions` |
| daily 04:00 | `compliance.tasks.check_periodic_reviews` |

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
   `sync_procedure_templates` and `asset_sync --seed-only`.
7. Open `/admin/operators/operator/` and complete identity, deployment mode and
   payment rails before inviting anyone. Enter the changelist, not
   `/admin/operators/operator/1/change/`: only `OperatorAdmin.changelist_view`
   seeds the row, so on a fresh install the change URL redirects to `/admin/`.
8. Confirm a worker is running; check the deployment, issuance and confirmation
   sweeps appear in its log.
9. Confirm `GET /health/` answers 200 and `GET /api/operator/` returns 401
   anonymously.
10. Leave the `trading_enabled` feature flag off; while it is off the
    middleware refuses with 403 any request, of any method, whose path starts
    with one of five prefixes
    (`/api/v1/trading/{orders,wallets,transfers,swaps,events}/`). The read-only
    market routes (`tokens/`, `stablecoins/`) and the whitelist status route sit
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
