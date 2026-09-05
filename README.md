# Ledova

Ledova is an experimental, open-source reference implementation for modelling
allowlist-gated share tokens and settlement flows. The repository contains
Solidity contracts, a Django API, web applications, a React Native client, and
a shared TypeScript package.

Ledova is the sanitized public continuation of the earlier private Blueberry
codebase. The transition preserves its existing architecture and behaviour
where practical rather than rebuilding the platform from scratch. Secrets,
production configuration, private operations, and private data do not belong
here; publication blockers are addressed now, while broader production
hardening remains tracked in [ISSUES.md](./ISSUES.md).

> **Experimental and unaudited.** Use Ledova only with synthetic data on a
> local development chain or supported public testnet. It is not production
> ready and must not be used with real funds, securities, companies, identities,
> wallets, or personal information.

**▶ [Watch a one-minute walkthrough](https://ledova.io/#demo)** of the local
stack — sign-up, onboarding, watch-only wallets, and market data — or run it
yourself with the quick start below.

Ledova does not represent a real asset, issuer, reserve, custodian, company
register, licensed service, or regulated offering. Nothing in this repository
is legal, financial, or investment advice, and no claim of regulatory
compliance or legal recognition is made.

## Repository layout

| Path | Contents |
| --- | --- |
| `contracts/` | Solidity contracts and local/testnet deployment examples |
| `backend/` | Django REST API and PostgreSQL-backed background jobs |
| `dashboard/` | React and Vite application demo |
| `marketing/` | Static project site |
| `mobile/` | Experimental Expo application |
| `packages/` | Shared TypeScript constants, types, services, and utilities |

The current verified checkpoint and next task are recorded in
[HANDOVER.md](./HANDOVER.md). Backend layering and style rules live in
[backend/docs/CONVENTIONS.md](./backend/docs/CONVENTIONS.md).

## Quick start

Prerequisites: Docker with Compose and Python 3.13. From the repository root:

```bash
python3 scripts/init-local-env.py
docker compose up --build
```

With Docker images already cached, the local demo should start in under five
minutes. A first run may take longer while Docker downloads and builds images.
The `migrate` service also seeds the compliance monitoring rules, the alert
procedure templates and the supported assets on every start; if you run the
backend outside Docker (`make run` in `backend/`), run `python manage.py migrate`,
`python manage.py sync_monitoring_rules`, `python manage.py sync_procedure_templates`
and `python manage.py asset_sync --seed-only` once first.

The initializer creates ignored, owner-only local environment files and
generates the required development secrets without printing them. It never
overwrites an existing environment file.

Once the containers are ready:

- Dashboard: <http://localhost:5174>
- Marketing site: <http://localhost:5173>
- API: <http://localhost:8000>

Stop the stack with `docker compose down`.

The dashboard authenticates with cookies, so its origin must be listed in the
backend's `DJANGO_CSRF_TRUSTED_ORIGINS` (the template already lists
`http://localhost:5174`); cookie-authenticated writes from any other origin are
rejected with `403 CSRF Failed`.

Sign-up requires an email verification code. The local stack has no email
provider configured: with `SENDGRID_API_KEY` empty the backend hands mail to
Django's email backend, which under `DEBUG=true` (the local default) prints the
message, six-digit code included, to the backend log
(`docker compose logs -f backend`). A code is valid for ten minutes and five
attempts; request a new one with "Resend" if it lapses. Outside `DEBUG` a real
SendGrid configuration is required.

To run the contract suite independently:

```bash
cd contracts
npm ci
npx hardhat test
```

### Local chain

Share tokens are created through the `ShareTokenFactory`, shares are minted
on allotment (never at deployment) up to the authorized cap, and only wallets
on the `WhitelistRegistry` can receive them. To exercise that against a real
node:

```bash
cd contracts && npx hardhat node          # terminal 1, chain id 31337
npm --prefix contracts run deploy:local:core   # terminal 2, writes .deployed-contracts.env
```

Copy the four addresses from `.deployed-contracts.env` into `backend/.env`
together with `BLOCKCHAIN_RPC_URL`, `BLOCKCHAIN_CHAIN_ID=31337` and the
Hardhat account #0 key as `BLOCKCHAIN_OPERATOR_KEY` (see
`backend/.env.example`). `make chain-test` does all of that unattended: it
starts a node, deploys the core contracts, runs
`backend/tokens/tests/test_chain_integration.py` (deploy, whitelist, issue,
capital increase, pause, idempotent redeploy, recovery after a crash between
sending the create transaction and its receipt, a mint, capital increase or
pause whose receipt is lost after it mined) and stops the node. The same module
is skipped by the ordinary test suite and runs in CI. `CHAIN_TEST_PORT` moves
the node; `CHAIN_TEST_SETTINGS=ledova_backend.settings.test_postgres` (with the
`POSTGRES_*` variables set) runs it on PostgreSQL, which adds the two-worker
capital-increase case that needs real row locks; CI runs both.

## Safety defaults

- Local development and supported public testnets only; bundled mainnet
  deployment configuration is intentionally absent.
- Trading mutations are disabled by default. Enabling the feature flag does
  not make the trading implementation safe for production.
- Provider credentials, signer keys, deployment addresses, and private data
  are not included. Keep filled environment files outside version control.
- Client-prefixed variables such as `VITE_` and `EXPO_PUBLIC_` are public build
  configuration and must never contain secrets.

Important security and correctness work is intentionally deferred to
[ISSUES.md](./ISSUES.md). Do not expose this software as a public multi-user
service until those items have been addressed and independently reviewed.

## Contributing

Issues and pull requests are welcome. Please keep examples synthetic and avoid
including credentials, private endpoints, production identifiers, or personal
data in code, fixtures, screenshots, logs, or Git history.

## License

Licensed under the [Apache License 2.0](./LICENSE).
