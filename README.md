# Ledova

Ledova is an experimental, open-source reference implementation for modelling
allowlist-gated share tokens and settlement flows. The repository contains
Solidity contracts, a Django API, web applications, a React Native client, and
shared TypeScript packages.

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

## Quick start

Prerequisites: Docker with Compose and Python 3.13. From the repository root:

```bash
python3 scripts/init-local-env.py
docker compose up --build
```

With Docker images already cached, the local demo should start in under five
minutes. A first run may take longer while Docker downloads and builds images.

The initializer creates ignored, owner-only local environment files and
generates the required development secrets without printing them. It never
overwrites an existing environment file.

Once the containers are ready:

- Dashboard: <http://localhost:5174>
- Marketing site: <http://localhost:5173>
- API: <http://localhost:8000>

Stop the stack with `docker compose down`.

Sign-up requires an email verification code. The local stack has no email
provider configured; with `DEBUG=true` (the local default) the code `000000`
is accepted so the flow can be completed offline. Outside `DEBUG`, a real
SendGrid configuration is required and the bypass is disabled.

To run the contract suite independently:

```bash
cd contracts
npm ci
npx hardhat test
```

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
