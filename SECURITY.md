# Security Policy

How to report a vulnerability in Ledova, and what is in scope.

## Dependency advisories

CI fails on a new production advisory. `npm audit --omit=dev` runs at the
repository root and in `marketing/` and `contracts/`, where it must stay
completely clean, and in `mobile/`, where it must stay free of criticals.
`pip-audit` runs against `backend/requirements.txt`. `make audit` runs the same
checks locally.

`mobile/` carries advisories that are accepted rather than fixed, because no
forward version resolves them:

- **The Expo and Metro toolchain.** Most of the remaining highs reach the tree
  through `expo`, `@expo/cli`, `metro` and their dependencies, and clearing
  them needs an Expo SDK major upgrade. That is deliberately out of scope here:
  the SDK version is entangled with client work, and it belongs in its own
  change. These are build-time dependencies of a developer machine, not code
  shipped in the app.
- **The base58 and elliptic-curve chain.** `base-x`, `bs58` and `elliptic` have
  no fixed version published. The repository is local and testnet only, trading
  is disabled by default, and the app signs testnet transactions.
- **`pytest` in the backend tree.** `bitcoin-message-tool` declares `pytest` as
  a runtime dependency rather than a test one, so a production install pulls it
  in. `PYSEC-2026-1845` is ignored by id in the CI step: the application never
  imports `pytest`, and the advisory needs it to be running. Adding `pytest` to
  `requirements.txt` to force a fixed version would put an unimported package
  in production dependencies, which the coding rules forbid.

Every one of these is revisited before any mainnet or store-distributed build.
None of them is a reason to relax the gate; a new advisory outside these
categories fails CI.

## Reporting a vulnerability

Report vulnerabilities privately through
[GitHub's private vulnerability reporting](https://github.com/RonildoBraga/ledova/security/advisories/new)
for this repository. Do **not** open a public issue for a security problem.

You should receive an acknowledgement within a few days. This is a spare-time
source-available project, so please allow a reasonable window for a fix before any
public disclosure.

## Scope and expectations

Ledova is an experimental, unaudited reference implementation intended for local
and public-testnet use only. It is not operated as a hosted service, and it
makes no production-security or compliance claims.

Known, deliberately deferred security work is tracked publicly in the issues
labeled [`deferred-hardening`](https://github.com/RonildoBraga/ledova/issues?q=is%3Aopen+label%3Adeferred-hardening).
Reports that duplicate an item already listed there are still welcome, but will
likely be folded into the existing issue rather than fixed immediately.

## Out of scope

- Vulnerabilities in third-party dependencies without a demonstrated impact on
  this codebase. Please report those upstream.
- Findings that only apply when the software is deployed contrary to its
  documented testnet-only, non-production intent.
