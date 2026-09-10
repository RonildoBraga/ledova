# Ledova

## The problem

Private company shares are difficult to issue, manage, transfer, and invest in compared with publicly traded shares. Ownership records, investor onboarding, payments, share registries, and transfers can involve multiple disconnected systems and significant manual administration.

Companies also have limited control over the infrastructure through which their private shares are offered and managed.

## The Ledova solution

Ledova is a platform for creating and operating digital private equity markets.

Companies can represent their shares as blockchain-based tokens and use Ledova to manage the lifecycle of those shares — from issuance and investor onboarding through ownership tracking and transfers.

Ledova can be deployed in different ways. A company could operate its own Ledova instance and maintain direct control over its investors, share issuance, and registry. Alternatively, a platform operator or registry provider could operate Ledova on behalf of multiple companies.

Investors don't need to be crypto-native. They can invest using AUD/fiat or supported stablecoins, while Ledova handles the connection between the investment, the tokenized shares, and the company's ownership registry.

## Core features

1. Company onboarding — Create and manage companies and their equity structure.
2. Tokenized shares — Issue blockchain tokens representing shares or classes of shares in a private company.
3. Investor onboarding — Register investors and support identity/KYC and compliance processes.
4. Capital raising — Allow eligible investors to purchase tokenized shares offered by companies.
5. Fiat and stablecoin payments — Support investment using AUD/fiat as well as supported stablecoins.
6. Digital share registry — Maintain an auditable record of shareholders, holdings, issuances, and transfers.
7. Share transfers — Allow permitted transfers of tokenized shares between investors while enforcing the company's rules.
8. Investor portfolios — Give investors a view of their private-company holdings and transaction history.
9. Company dashboard — Give issuers visibility into shareholders, capital raised, ownership, transactions, and token supply.
10. Compliance controls — Provide KYC/AML, investor eligibility, transfer restrictions, and other controls required by the operator.
11. Self-hosted or multi-company operation — A company can operate Ledova for itself, or an operator can provide the infrastructure and registry service to multiple issuers.
12. Crypto wallet functionality — Support sending, receiving, and managing the blockchain assets required to interact with the platform.

> **Experimental and unaudited.** Use Ledova only with synthetic data on a local
> development chain or a supported public testnet. It is not production ready
> and must not be used with real funds, securities, companies, identities,
> wallets or personal information. It does not represent a real asset, issuer,
> reserve, custodian, company register, licensed service or regulated offering,
> and nothing here is legal, financial or investment advice.

## Who it is for

| Role | What they do |
| --- | --- |
| Operator | Hosts the deployment, runs the Django admin, holds the deployer key, receives investor payments in AUD or in a supported stablecoin |
| Company | Registers, is approved, deploys a share token, issues shares up to its authorized cap |
| Investor | Verifies identity, is whitelisted, holds shares in a verified EVM wallet |

Shares are minted on allotment as whole units; fractional shares are not
supported. The authorized share count is the cap; the contract's total supply
is what has actually been issued. The API retains `totalSupply` as a historical
name for the authorized cap and reports issued shares as `issuedSupply`.
Only whitelisted addresses can receive a share token, enforced by the contract
on every transfer.

## Two deployment modes

The operator row records which shape a deployment is
(`/admin/operators/operator/`, which seeds the row and redirects to it):

- **Single issuer** — one company runs its own instance for its own shares.
- **Registry** — a provider hosts many companies on one instance. This is the
  default.

Both run the same code and the same isolation rules; the mode is configuration,
not a fork.

## Repository layout

| Path | Contents |
| --- | --- |
| `contracts/` | Solidity contracts, Hardhat tests, local and testnet deployment scripts |
| `backend/` | Django REST API, Django admin, PostgreSQL-backed background jobs |
| `dashboard/` | React and Vite web client |
| `mobile/` | Expo application |
| `marketing/` | Static project site |
| `packages/` | `@ledova/shared`, the TypeScript constants, types, services and utilities both clients use, and `packages/scripts/` which generates the CSS design tokens |
| `docs/` | Architecture, operations and roadmap |
| `scripts/` | Local environment bootstrapper and the comment gate |

## Quick start

Prerequisites: Docker with Compose, and Python 3.13. From the repository root:

```bash
python3 scripts/init-local-env.py
docker compose up --build
```

The initializer creates owner-only, gitignored `.env` files from the
`.env.example` templates and generates the development secrets without printing
them. It never overwrites an existing environment file. `make init-local` and
`make dev-up` do the same two steps through the Makefile.

The `migrate` service runs the migrations and then seeds the compliance
monitoring rules, the alert procedure templates and the supported assets on
every start. Running the backend outside Docker (`make run` in `backend/`)
means running those four commands by hand once; see
[docs/OPERATIONS.md](docs/OPERATIONS.md).

Once the containers are ready:

- Dashboard: <http://localhost:5174>
- Marketing site: <http://localhost:5173>
- API: <http://localhost:8000>

Stop the stack with `docker compose down` or `make dev-down`.

Two things catch people out on a first run:

- The dashboard authenticates with cookies, so its origin must be listed in
  `DJANGO_CSRF_TRUSTED_ORIGINS` (the template already lists
  `http://localhost:5174`). Cookie-authenticated writes from any other origin
  are rejected with `403 CSRF Failed`.
- Sign-up requires an emailed six-digit code, and the local stack has no email
  provider. With `SENDGRID_API_KEY` empty and `DEBUG=true` the backend prints
  the message, code included, to its log (`docker compose logs -f backend`). A
  code lasts ten minutes and five attempts; use "Resend" if it lapses.

Common Makefile targets, from the repository root:

| Command | Does |
| --- | --- |
| `make install` | `npm ci` for the root workspace, `contracts`, `marketing` and `mobile` |
| `make install-backend` | Install the backend development dependencies |
| `make build` | Build the dashboard, the marketing site and the contracts |
| `make check` | Run `check-comments`, install the backend development dependencies (`requirements-dev.txt`), then type-check every workspace and run Django's `manage.py check` |
| `make check-comments` | Fail on any comment or docstring in the source trees that carry none |
| `make test` | Workspace and contract tests |
| `make chain-test` | The real-chain backend test against a Hardhat node |
| `make generate-tokens` | Regenerate the CSS design tokens from `packages/shared` |

`make help` lists the common ones; the Makefile also has `check-local-env`,
`contracts-compile` and `contracts-test`.

## Local chain

Share tokens are created through the `ShareTokenFactory`, minted on allotment up
to the authorized cap, and only wallets on the `WhitelistRegistry` can receive
them. To exercise that against a real node, in two terminals:

```bash
cd contracts && npx hardhat node               # chain id 31337
npm --prefix contracts run deploy:local:core   # writes .deployed-contracts.env
```

Then point `backend/.env` at the node and the deployed addresses;
[docs/OPERATIONS.md](docs/OPERATIONS.md#chain-configuration) has the variable
list and the Base Sepolia equivalent.

`make chain-test` does all of that unattended, running
`backend/tokens/tests/test_chain_integration.py` (deploy, whitelist, issue,
capital increase, pause, idempotent redeploy and recovery from lost receipts)
against a node it starts and stops. That module is skipped by the ordinary
suite; CI runs it on SQLite and again on PostgreSQL.

To run the contract suite on its own:

```bash
cd contracts && npm ci && npx hardhat test
```

## Where to go next

| Where | For |
| --- | --- |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Contracts, backend apps and layers, clients, the shared package, the issuance data flow, auth, tenancy, uploaded files |
| [docs/GATES.md](docs/GATES.md) | The coding rules, and the nine gate scripts documented here, each with what it refuses and what it does not cover |
| [docs/TRAPS.md](docs/TRAPS.md) | Tests and measurements that looked like checks and were not, kept as recognisable shapes |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | Operator setup, the environment variable reference, seeds, keys, chain configuration, background jobs, migration notes, deploy checklist |
| [docs/ROADMAP.md](docs/ROADMAP.md) | The phases and the product decisions taken |
| [docs/PRACTICES.md](docs/PRACTICES.md) | How work is done here: the discipline, building, reviewing, driving the product, the four audits, triage and design notes |
| [GitHub issues](https://github.com/RonildoBraga/ledova/issues) | Open high-risk work, deferred deliberately — labeled [`deferred-hardening`](https://github.com/RonildoBraga/ledova/issues?q=is%3Aopen+label%3Adeferred-hardening) |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Workflow, gates and pull request rules |
| [SECURITY.md](SECURITY.md) | Reporting a vulnerability |

## Safety defaults

- Local development and supported public testnets only. Startup refuses any EVM
  chain id outside 1337, 31337, 84532 and 11155111, and any Bitcoin network
  other than `test` and `regtest`. Mainnet deployment configuration is
  deliberately absent.
- While the `trading_enabled` feature flag is off,
  `backend/feature_flags/middleware.py` refuses with 403 any request, of any
  method, whose path starts with one of five prefixes:
  `/api/v1/trading/{orders,wallets,transfers,swaps,events}/`. The read-only
  market route (`tokens/`) and the whitelist status route sit outside the gate
  by design. Turning the flag on does not make the trading
  implementation safe.
- Provider credentials, signer keys, deployment addresses and private data are
  not included. Keep filled environment files out of version control.
- `VITE_` and `EXPO_PUBLIC_` variables are public build configuration and must
  never hold a secret.

Issues are tracked on GitHub, not in this repository. Important security and
correctness work is deliberately deferred to the
[`deferred-hardening`](https://github.com/RonildoBraga/ledova/issues?q=is%3Aopen+label%3Adeferred-hardening) issues, each of which names where it lives in
the code. Do not expose this software as a public multi-user service until
those items have been addressed and independently reviewed.

## Contributing

Issues and pull requests are welcome. Keep examples synthetic, and keep
credentials, private endpoints, production identifiers and personal data out of
code, fixtures, screenshots, logs and Git history. Read
[CONTRIBUTING.md](CONTRIBUTING.md) first.

## Sponsor

Ledova is built and maintained by Ronildo da Rocha Braga Junior, who holds the
copyright.

[Blueberry Money](https://github.com/RonildoBraga/ledova) sponsors the project
and intends to be the first company to operate Ledova as hosted infrastructure.
Sponsorship funds the work; it does not transfer ownership, and it buys no
control over what the project accepts or where it goes.

## License

Licensed under the [Functional Source License, Version 1.1, ALv2 Future
License](LICENSE) — FSL-1.1-ALv2. The full terms are short and worth reading.
In outline:

| You may, freely and without asking | You may not |
| --- | --- |
| Read, fork, modify and redistribute the source | Offer Ledova to others as a commercial product or service that substitutes for it, or for a service offered using it |
| Run it for your own internal use, including a company operating its own share registry | Offer the same or substantially similar functionality as a commercial product or service |
| Use it for non-commercial research or education | |
| Provide professional services to someone else who is using it under these terms | |

**Every release becomes Apache 2.0 two years after it is published.** That grant
is irrevocable and is part of the licence, so nothing here is enclosed
permanently — it is delayed, not withheld.

Releases before 2026-09-10 were made under the Apache License 2.0 and stay
available under it.

The licence does not grant any right to the Ledova or Blueberry Money names,
trade marks or product names, beyond identifying the origin of the software.
