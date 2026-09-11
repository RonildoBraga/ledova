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
- Every work item, including owner-requested changes, is tracked in a GitHub
  issue. Reuse an existing issue when its scope fits; otherwise create one before
  implementation.
- Keep issues concise: the problem or context, intended outcome, and short
  completion checks. The assistant may open, update and triage issues without a
  separate approval step.
- Link pull requests to their issues and close an issue only when its work is
  complete. Record distinct problems discovered along the way in follow-up
  issues, checking for an existing issue first.

## Development setup

The [README quick start](README.md#quick-start) covers the full local stack.
In short:

| Target | Commands |
| --- | --- |
| Whole stack in Docker | `make init-local && make dev-up` |
| Dashboard and shared package | `npm ci && npm run dev:dashboard` (the dashboard compiles `packages/shared` from source; there is no build step) |
| Backend outside Docker | `cd backend && make install && make run`, with a `.env` present |
| Contracts | `cd contracts && npm ci && npx hardhat compile && npx hardhat test` |
| Mobile | `cd mobile && make install && make start`; native builds/probes: [docs/MOBILE.md](docs/MOBILE.md) |

Local compilation and the contract tests need no credentials.
[docs/OPERATIONS.md](docs/OPERATIONS.md) documents every environment variable.

## Making changes

1. Branch from `main` (`fix/whitelist-check`, `docs/quickstart`). Contributors
   without repository write access use a fork.
2. Keep pull requests small and focused: one logical change each.
3. Add or update tests for any behaviour change. Security and correctness fixes
   come with a regression test. A new detail route or custom action also needs a
   cross-tenant row in `backend/shared/tests/test_cross_tenant_routes.py`.
4. Follow the coding rules in
   [docs/GATES.md](docs/GATES.md#the-rules). The one that
   surprises people most: **source carries no comments and no docstrings**. Only
   functional directives the tooling reads (`# noqa`, `eslint-disable`,
   `// SPDX-License-Identifier` and the rest of the list) are allowed, and that
   list is closed. There is no "unless it is really needed" exception: if a line
   seems to need explaining, rename it or add a test. `make check-comments`
   fails on anything else, so run it before you push. Configuration and
   documentation files keep their comments.
5. Write a clear pull request description: what changed, why, and how you
   verified it. Link the issue it addresses (`Closes #12` when the PR completes
   the issue, otherwise `Refs #12`).

## Review and merge

The owner and assistant work as a small team. Within agreed work, the assistant
may choose implementation details, branches and task-specific delegation, and
carry changes through testing, pull requests and merge without repeated owner
permission. This applies to all engineering paths, including authentication,
wallets and payments.

This workflow records the required reviews and checks on the PR without requiring
enforced branch-protection or approval settings; revisit enforcement if the team
grows.

1. **Everything lands through a pull request.** Nothing is pushed to `main`
   directly, documentation included.
2. **The author records what they checked** in the description before asking for
   review: the commands run and their results, what could not be reproduced, and
   what was deliberately not checked. An unstated gap reads as a checked one.
3. **One independent review, at the commit that will merge.** The reviewer is
   another human or agent, not the author. A PR comment recording the reviewer's
   identity, verdict and head SHA is sufficient; a separate GitHub account or
   formal GitHub approval is not required by project policy. If the branch
   moves, either show the content is unchanged or have the delta read.
4. **Required CI green, on a branch up to date with `main`.** Green on the branch
   and green on `main` separately do not establish that the two are green
   together.
5. **Product and legal decisions remain the repository owner's.** Live
   deployment, live database migrations, signer activation and real-funds use
   also require the owner's explicit direction.

How to establish that a change does what it claims is a separate question, and is
in [docs/PRACTICES.md](docs/PRACTICES.md).

## Gates

Run these locally before opening a pull request. Most are also CI gates; the
exceptions are noted below the table.

| Area | Command |
| --- | --- |
| All source gates at once | `make check` from the root, which also type-checks every workspace; see the [gate inventory](docs/GATES.md#every-gate-and-where-its-rule-is-written) |
| Comments and docstrings | `make check-comments` from the root (no dependencies needed) |
| Type-check scripts | `make check-type-check` from the root (no dependencies needed) |
| Backend layers | `make check-layers` from the root (no dependencies needed) |
| Logging privacy | `make check-logging` and `make test-gates` from the root (no dependencies needed) |
| Connection binding | `make check-connection-binding` from the root |
| Error bodies | `make check-error-bodies` from the root |
| Schema responses | `make check-schema-responses` from the root |
| Test shadowing | `make check-test-shadowing` from the root |
| Documentation | `make check-docs` from the root |
| Self-imports and mobile resolution | `make check-self-imports`, `npm --prefix mobile run check:resolution` |
| API schema snapshot | `make check-api-schema` generates the schema using the [pinned schema environment](docs/GATES.md#the-api-type-drift-gate) |
| API type drift | `make check-api-types` reads an existing generated schema at `SCHEMA`; it does not generate one |
| Client operation coverage | `make check-client-operations` uses Node and the committed schema after root dependencies are installed |
| Dependency advisories | `make audit` from the root |
| Everything JavaScript | `make build`, `make check`, `make test` from the root. `make check` installs any workspace whose `node_modules` is missing before it runs |
| Design tokens | `make generate-tokens`, then confirm `dashboard/src/styles/tokens.css` and `marketing/src/tokens.css` are unchanged |
| Backend | from `backend/`: `make lint` (black, isort, flake8), `make check`, `make test` |
| Backend migrations | from `backend/`: `python manage.py makemigrations --check --dry-run` |
| Contracts | from `contracts/`: `npm run format:check && npx hardhat test` |
| Lint | `make lint` from the root (ESLint across the workspaces, solhint for the contracts) |
| Real chain | `make chain-test` from the root |
| Dashboard smoke | `make build`, then `make smoke` from the root |

Each workspace resolves from its own `node_modules`, so running a workspace's
check by hand needs that workspace installed. `npm --prefix mobile run type-check`
is the one that catches people out: without `npm ci` inside `mobile/` it fails on
`expo/tsconfig.base` before reading a line of project code, which reads as a type
error in the project and is not. `make check` now installs what it needs, so reach
for that if a bare workspace command fails on something you did not write. That
check earns its place — it has caught a narrowing the dashboard's own type-check
compiled happily.

Local-only: `.github/workflows/ci.yml` has no format step for any workspace, so
`npm run format:check` is yours to run. Linting is no longer in that list — CI
runs `make lint` on every pull request.

CI runs `make lint`, `make test` (dashboard, `packages/shared`, mobile and
contracts) and `make smoke` on every pull request. It additionally runs the whole Django suite
on PostgreSQL, the SQLite migration tests, and `make chain-test` twice, the
second time on PostgreSQL. The source gates are their own CI job, running the
scripts assigned to it in the [gate inventory](docs/GATES.md#every-gate-and-where-its-rule-is-written)
and then `make test-gates`, so a stray comment, a new layer violation or a log
line that can carry a credential fails the pipeline without waiting for
anything to be built.

## Reporting security issues

Do not open a public issue for a vulnerability. Use GitHub's private
vulnerability reporting on this repository (Security, then *Report a
vulnerability*). See [SECURITY.md](SECURITY.md).

## Licensing of contributions

By submitting a contribution you agree that it is licensed under the project's
[Functional Source License, Version 1.1, ALv2 Future License](LICENSE) and that
you have the right to submit it under that license. Like every other release,
your contribution becomes available under the Apache License 2.0 two years after
it is published.

Ledova is source-available rather than open source in the OSI sense: the licence
permits any use except competing with the project commercially, and converts to
Apache 2.0 on a fixed two-year schedule. Copyright is held by Ronildo da Rocha
Braga Junior. The full terms are set out under **License** in
[README.md](README.md).

Ledova makes no claim of regulatory compliance or legal recognition.
Contributions are volunteered on that basis.
