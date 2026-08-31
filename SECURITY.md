# Security Policy

## Reporting a vulnerability

Please report vulnerabilities privately through
[GitHub's private vulnerability reporting](https://github.com/RonildoBraga/ledova/security/advisories/new)
for this repository. Do **not** open a public issue for security problems.

You should receive an acknowledgement within a few days. As this is a
spare-time open-source project, please allow a reasonable window for a fix
before any public disclosure.

## Scope and expectations

Ledova is an **experimental, unaudited reference implementation** intended for
local and public-testnet use only. It is not operated as a hosted service, and
it makes no production-security or compliance claims.

Known, deliberately deferred security work is tracked publicly in
[ISSUES.md](ISSUES.md) and in the issues labeled
[`deferred-hardening`](https://github.com/RonildoBraga/ledova/issues?q=label%3Adeferred-hardening).
Reports that duplicate an item already listed there are still welcome, but
will likely be folded into the existing issue rather than fixed immediately.

## Out of scope

- Vulnerabilities in third-party dependencies without a demonstrated impact
  on this codebase (please report those upstream).
- Findings that only apply when the software is deployed contrary to its
  documented testnet-only, non-production intent.
