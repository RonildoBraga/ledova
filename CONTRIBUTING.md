# Contributing to Ledova

Thanks for your interest. Ledova is an early-stage, **experimental, unaudited,
testnet-only** reference implementation, so there is a lot of surface to
improve — and contributions that make it more correct, more secure, better
tested, and better documented are especially welcome.

Please read this whole page before opening your first pull request.

## Ground rules

- **Testnet and synthetic data only.** Never contribute code, configuration,
  tests, or docs that assume real funds, real securities, real personal data,
  or a mainnet deployment target. Chain guards that fail closed on mainnet IDs
  are intentional — do not weaken them.
- **No secrets, ever.** Do not commit `.env` files, private keys, seed phrases,
  API tokens, real personal data, or internal infrastructure identifiers. Only
  `.env.example` templates with blank values belong in the repo.
- **Trading and mutation flows are disabled by default** while the issues in
  the tracker (see below) are open. That default is containment, not a bug to
  "fix" by enabling them.
- Be respectful and constructive. Assume good faith.

## Where to start

- Browse the **[open issues](https://github.com/RonildoBraga/ledova/issues)**.
  The items labeled **`deferred-hardening`** are the known high-risk work
  intentionally deferred from this release — they describe the redesigns
  required before any multi-user or real-value use. `ISSUES.md` is the
  human-readable index of the same list.
- For anything substantial, **open an issue to discuss it first** so we can
  agree on the approach before you invest time.

## Development setup

The `README.md` quick-start covers the full local stack. In short:

- **Contracts:** `cd contracts && npm ci && npx hardhat compile && npx hardhat test`
- **Backend + web stack (Docker):** `make init-local && make dev-up`
- **Shared package + dashboard:** `npm ci && npm run dev:dashboard` (the dashboard compiles `packages/shared` from source; no build step)

Copy each `.env.example` to a local `.env` and fill in your own values before
running that component. Local compilation and contract tests do not need any
credentials.

## Making changes

1. **Fork** the repo and create a branch from `main`
   (e.g. `fix/whitelist-check`, `docs/quickstart`).
2. Keep pull requests **small and focused** — one logical change per PR.
3. **Add or update tests** for any behavior change. Security- and
   correctness-related changes should come with a regression test.
4. **Run the checks locally** before pushing:
   - Backend (from `backend/`): `make lint && make check && make test`; CI
     also runs the suite on PostgreSQL. Follow
     [backend/docs/CONVENTIONS.md](./backend/docs/CONVENTIONS.md) for
     layering and style.
   - JS/TS workspaces: the package's `lint`, `type`/build, and `test` scripts.
   - Contracts: `npm run lint && npm run format:check && npx hardhat test`.
5. Write a clear PR description: what changed, why, and how you verified it.
   Reference the issue it addresses (e.g. `Closes #12`).

## Reporting security issues

**Do not open a public issue for a security vulnerability.** Use GitHub's
**private vulnerability reporting** on this repository
(Security → *Report a vulnerability*). Include reproduction steps and affected
paths. Because this is an unaudited experimental project, please still avoid
using it with anything of real value.

## Licensing of contributions

By submitting a contribution, you agree that it is licensed under the project's
**[Apache License 2.0](./LICENSE)**, and that you have the right to submit it
under that license.

---

Ledova is an independent open-source project and makes no claim of regulatory
compliance or legal recognition. Contributions are volunteered on that basis.
