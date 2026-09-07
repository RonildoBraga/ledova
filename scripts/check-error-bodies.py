#!/usr/bin/env python3
"""Fail when an API error response would carry an exception's own text.

The rule and its scope are stated in docs/ARCHITECTURE.md under "The error body
gate". This script is the mechanical half of that rule; keep the two in step.

An `APIException` subclass raised with an argument is served to the caller as the
response body by `shared/api/exceptions.py`. When that argument is built from a
caught exception's text, the body is whatever the underlying library chose to
say - and for a `requests` failure that is the request URL, which for this
deployment carries the node provider's API key as a path segment. Measured on
`main` in #243:

    STATUS 500
    BODY   {'detail': 'Transfer preparation failed: Max retries exceeded with url:
            https://base-sepolia.g.alchemy.com/v2/<the key>'}

`check-logging.py` already refuses handing a whole provider response body to a
log formatter, on the reasoning that a whole body is whatever the provider chose
to send. The same reasoning applies with more force to a response body, which
reaches a caller rather than an operator.

The rule is decidable from syntax. Inside an `except ... as name:` handler, an
`APIException` subclass may not be constructed from `name`: not the bare name,
not `str(name)`, not an f-string interpolating it, not `repr()` or `.format()`
of it, and not a local assigned from any of those.

Every subclass already carries a `default_detail`, so the fix is to raise it bare
and log the diagnostic. What is lost is the part that was never for the caller:
the reasons a caller can act on are separate exceptions raised above the generic
branch, and they keep their messages.

The subclass set is collected from the source rather than listed here, following
`APIException` through subclassing, so a new exception module is covered without
an edit.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"

SERVES_EXCEPTION_TEXT = "serves-exception-text"

RULES = {
    SERVES_EXCEPTION_TEXT: (
        "builds an API error body from a caught exception's text, so the response carries whatever "
        "the underlying library chose to say. Raise the exception bare - it has a default_detail - "
        "and log the diagnostic instead."
    ),
}

# Deriving a caller-safe message from an exception is allowed, but only through a
# function that is about producing one. decode_exception_to_message extracts a hex
# blob, decodes a known revert reason from it, and returns that or a stated
# default - it never returns the exception's own text, so a URL carrying a
# provider key cannot reach a caller through it. Adding a name here is a claim
# about that function, and the claim has to be true.
SANITISERS = {"decode_exception_to_message"}

# Empty, and it is meant to stay that way. It held the five native and ERC-20 send
# paths in wallets/services/transfers.py, which #274 fixed the same way as the
# eighteen here - a fixed message and a logged diagnostic - so the count fell to
# zero and the gate said so rather than letting a satisfied pin sit here forever.
LEGACY: dict[str, int] = {}


def api_exception_names() -> set[str]:
    found: set[str] = set()
    edges: list[tuple[str, str]] = []

    for path in sorted(BACKEND.rglob("*.py")):
        if "migrations" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for base in node.bases:
                rendered = ast.unparse(base)
                if rendered.split(".")[-1] == "APIException":
                    found.add(node.name)
                else:
                    edges.append((node.name, rendered.split(".")[-1]))

    widened = True
    while widened:
        widened = False
        for child, base in edges:
            if base in found and child not in found:
                found.add(child)
                widened = True
    return found


def _derives_from(node: ast.AST, caught: str, tainted: set[str]) -> bool:
    """Whether this expression carries the caught exception's text."""
    for inner in ast.walk(node):
        if isinstance(inner, ast.Name) and inner.id in ({caught} | tainted):
            return True
    return False


def _sanitised(value: ast.AST) -> bool:
    return (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id in SANITISERS
    )


def _tainted_locals(handler: ast.ExceptHandler, caught: str) -> set[str]:
    tainted: set[str] = set()
    for statement in ast.walk(handler):
        if not isinstance(statement, ast.Assign):
            continue
        if _sanitised(statement.value):
            continue
        if _derives_from(statement.value, caught, tainted):
            for target in statement.targets:
                if isinstance(target, ast.Name):
                    tainted.add(target.id)
    return tainted


def findings_in(tree: ast.AST, subclasses: set[str], relative: Path) -> list[str]:
    findings: list[str] = []

    for handler in [n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler)]:
        if not handler.name:
            continue
        caught = handler.name
        tainted = _tainted_locals(handler, caught)

        for statement in ast.walk(handler):
            if not isinstance(statement, ast.Call):
                continue
            if not isinstance(statement.func, ast.Name):
                continue
            if statement.func.id not in subclasses:
                continue
            arguments = list(statement.args) + [k.value for k in statement.keywords]
            if any(
                _derives_from(argument, caught, tainted)
                and not any(_sanitised(inner) for inner in ast.walk(argument))
                for argument in arguments
            ):
                findings.append(
                    f"{relative}:{statement.lineno} {statement.func.id}({caught}): "
                    f"{SERVES_EXCEPTION_TEXT}"
                )
    return findings


def scan() -> tuple[list[str], int]:
    subclasses = api_exception_names()
    findings: list[str] = []
    checked = 0

    for path in sorted(BACKEND.rglob("*.py")):
        parts = path.relative_to(BACKEND).parts
        if "migrations" in parts or "tests" in parts:
            continue
        checked += 1
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        findings += findings_in(tree, subclasses, path.relative_to(ROOT))

    return findings, checked


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--explain", action="store_true")
    if parser.parse_args().explain:
        for rule, explanation in RULES.items():
            print(f"{rule}: {explanation}")
        return 0

    findings, checked = scan()

    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding.split(":")[0]] = counts.get(finding.split(":")[0], 0) + 1

    new = {key: count for key, count in counts.items() if count > LEGACY.get(key, 0)}
    stale = sorted(key for key, pinned in LEGACY.items() if counts.get(key, 0) < pinned)

    if new:
        offenders = [f for f in findings if f.split(":")[0] in new]
        print(f"API error bodies built from an exception's text ({len(offenders)}):\n", file=sys.stderr)
        for finding in offenders:
            print(f"  {finding}", file=sys.stderr)
        print(f"\n  {SERVES_EXCEPTION_TEXT}: {RULES[SERVES_EXCEPTION_TEXT]}", file=sys.stderr)
        print(
            '\nThe rule and its scope are in docs/ARCHITECTURE.md, "The error body gate".',
            file=sys.stderr,
        )
        return 1

    if stale:
        print(f"These pinned counts are higher than what is there ({len(stale)}):\n", file=sys.stderr)
        for key in stale:
            print(f"  {key}: pinned {LEGACY[key]}, found {counts.get(key, 0)}", file=sys.stderr)
        return 1

    print(f"No API error body carries an exception's text, in {checked} files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
