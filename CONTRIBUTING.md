# Contributing to Ledova

How to set up, what the gates are, and what a pull request has to look like.

Ledova is an early-stage, experimental, unaudited, testnet-only reference
implementation, so contributions that make it more correct, more secure, better
tested and better documented are especially welcome. Please read this whole page
before opening your first pull request.

## Ground rules

- **Testnet and synthetic data only.** Never contribute code, configuration,
  tests or docs that assume real funds, real securities, real personal data or a
  mainnet deployment target. The chain guards that fail closed on unsupported
  chain ids are intentional; do not weaken them.
- **No secrets, ever.** No `.env` files, private keys, seed phrases, API tokens,
  real personal data or internal infrastructure identifiers. Only `.env.example`
  templates with blank values belong in the repository.
- **Trading routes are disabled by default** while the
  [`deferred-hardening`](https://github.com/RonildoBraga/ledova/issues?q=is%3Aopen+label%3Adeferred-hardening) issues are open. That default is containment,
  not a bug to "fix" by enabling them.
- Be respectful and constructive. Assume good faith.
  See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Where to start

- Issues are tracked on GitHub, not in this repository. Browse the
  [open issues](https://github.com/RonildoBraga/ledova/issues); the ones labeled
  [`deferred-hardening`](https://github.com/RonildoBraga/ledova/issues?q=is%3Aopen+label%3Adeferred-hardening) are the known high-risk work, each naming
  where it lives in the code. They need redesigns, not patches.
- For anything substantial, open an issue to discuss the approach first.

## Development setup

The [README quick start](README.md#quick-start) covers the full local stack.
In short:

| Target | Commands |
| --- | --- |
| Whole stack in Docker | `make init-local && make dev-up` |
| Dashboard and shared package | `npm ci && npm run dev:dashboard` (the dashboard compiles `packages/shared` from source; there is no build step) |
| Backend outside Docker | `cd backend && make install && make run`, with a `.env` present |
| Contracts | `cd contracts && npm ci && npx hardhat compile && npx hardhat test` |
| Mobile | `cd mobile && make install && make start` |

Local compilation and the contract tests need no credentials.
[docs/OPERATIONS.md](docs/OPERATIONS.md) documents every environment variable.

## Making changes

1. Fork, and branch from `main` (`fix/whitelist-check`, `docs/quickstart`).
2. Keep pull requests small and focused: one logical change each.
3. Add or update tests for any behaviour change. Security and correctness fixes
   come with a regression test. A new detail route or custom action also needs a
   cross-tenant row in `backend/shared/tests/test_cross_tenant_routes.py`.
4. Follow the coding rules in
   [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#coding-rules). The one that
   surprises people most: **source carries no comments and no docstrings**. Only
   functional directives the tooling reads (`# noqa`, `eslint-disable`,
   `// SPDX-License-Identifier` and the rest of the list) are allowed, and that
   list is closed. There is no "unless it is really needed" exception: if a line
   seems to need explaining, rename it or add a test. `make check-comments`
   fails on anything else, so run it before you push. Configuration and
   documentation files keep their comments.
5. Write a clear pull request description: what changed, why, and how you
   verified it. Reference the issue it addresses (`Closes #12`).

## Gates

Run these locally before opening a pull request. Most are also CI gates; the
exceptions are noted below the table.

| Area | Command |
| --- | --- |
| Comments and docstrings | `make check-comments` from the root (no dependencies needed) |
| Everything JavaScript | `make build`, `make check`, `make test` from the root |
| Design tokens | `make generate-tokens`, then confirm `dashboard/src/styles/tokens.css` and `marketing/src/tokens.css` are unchanged |
| Backend | from `backend/`: `make lint` (black, isort, flake8), `make check`, `make test` |
| Backend migrations | from `backend/`: `python manage.py makemigrations --check --dry-run` |
| Contracts | from `contracts/`: `npm run format:check && npm run lint && npx hardhat test` |
| Real chain | `make chain-test` from the root |

Local-only: `.github/workflows/ci.yml` has no contracts lint or format step, so
`npm run format:check` and `npm run lint` from `contracts/` are yours to run.
CI's `make test` runs `npm test` and `npm --prefix contracts test` only; root
`npm run lint` is not a gate either.

CI additionally runs the whole Django suite on PostgreSQL, the SQLite migration
tests, and `make chain-test` twice, the second time on PostgreSQL. The comment
gate is its own CI job, running `python scripts/check-comments.py` directly, so
a stray comment fails the pipeline without waiting for anything to be built.

## Reporting security issues

Do not open a public issue for a vulnerability. Use GitHub's private
vulnerability reporting on this repository (Security, then *Report a
vulnerability*). See [SECURITY.md](SECURITY.md).

## Licensing of contributions

By submitting a contribution you agree that it is licensed under the project's
[Apache License 2.0](LICENSE) and that you have the right to submit it under
that license.

Ledova is an independent open-source project and makes no claim of regulatory
compliance or legal recognition. Contributions are volunteered on that basis.
