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
SERVES_EXCEPTION_TEXT_TO_A_FIELD = "serves-exception-text-to-a-field"

RULES = {
    SERVES_EXCEPTION_TEXT: (
        "builds an API error body from a caught exception's text, so the response carries whatever "
        "the underlying library chose to say. Raise the exception bare - it has a default_detail - "
        "and log the diagnostic instead."
    ),
    SERVES_EXCEPTION_TEXT_TO_A_FIELD: (
        "hands a caught exception's text to a model method that writes a field a client-facing "
        "serializer exposes, so the response carries it in a 200 body rather than an error one. "
        "Pass a fixed note and keep the diagnostic in the log and on the operator-facing record."
    ),
}

# The same rule one layer out, and the receiver is how it is decided. A method name
# alone cannot say which model it is on: ReviewRequest.mark_failed writes
# review_notes, which two client serializers expose, while ShareIssuance and
# BlockchainTransaction both have a mark_failed that writes error_message, which no
# client serializer exposes. Each entry is a claim that this receiver is one of the
# operator-facing ones, and the claim has to be true.
ALLOWED_NOTE_RECEIVERS = {
    "issuance.mark_failed": "ShareIssuance.error_message; no client serializer exposes it",
    "issuance.mark_reverted": "ShareIssuance.error_message; no client serializer exposes it",
    "tx_record.mark_failed": "BlockchainTransaction.error_message; operator-facing",
    "tx_record.mark_outcome_unknown": "BlockchainTransaction.error_message; operator-facing",
    "tx_record.mark_reverted": "BlockchainTransaction.error_message; operator-facing",
    "entry.mark_failed": "WhitelistEntry.notes; no client serializer exposes it",
    "mint_request.mark_failed": "MintRequest has no serializer at all; it is reached through the admin",
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


def helpers_that_build_an_exception(subclasses: set[str]) -> set[str]:
    """Functions that construct an APIException subclass from one of their own parameters.

    A caught exception handed to one of these reaches a response body the same way
    it would from the handler, and the gate sees neither end: at the call site the
    callee is not a subclass, and inside the helper there is no handler for
    `_derives_from` to be asked about. #390 measured that on
    `whitelist/services/whitelist.py:_refuse`, where a rebase had restored the leak
    and only a test noticed.
    """
    helpers: set[str] = set()
    for path in sorted(BACKEND.rglob("*.py")):
        parts = path.relative_to(BACKEND).parts
        if "migrations" in parts or "tests" in parts:
            continue
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            parameters = {argument.arg for argument in node.args.args} - {"self", "cls"}
            if not parameters:
                continue
            for call in ast.walk(node):
                if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)):
                    continue
                if call.func.id not in subclasses:
                    continue
                arguments = list(call.args) + [k.value for k in call.keywords]
                if any(
                    isinstance(inner, ast.Name) and inner.id in parameters
                    for argument in arguments
                    for inner in ast.walk(argument)
                ) and not any(_sanitised(inner) for argument in arguments for inner in ast.walk(argument)):
                    helpers.add(node.name)
    return helpers


def fields_each_model_exposes() -> dict[str, set[str]]:
    exposed: dict[str, set[str]] = {}
    for path in sorted(BACKEND.rglob("serializers/*.py")):
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for outer in ast.walk(tree):
            if not isinstance(outer, ast.ClassDef):
                continue
            for meta in outer.body:
                if not (isinstance(meta, ast.ClassDef) and meta.name == "Meta"):
                    continue
                model = None
                named: set[str] = set()
                for statement in meta.body:
                    if not isinstance(statement, ast.Assign):
                        continue
                    targets = {t.id for t in statement.targets if isinstance(t, ast.Name)}
                    if "model" in targets:
                        model = ast.unparse(statement.value).split(".")[-1]
                    if "fields" in targets:
                        named |= {
                            element.value
                            for element in ast.walk(statement.value)
                            if isinstance(element, ast.Constant) and isinstance(element.value, str)
                        }
                if model:
                    exposed.setdefault(model, set()).update(named)
    return exposed


def note_methods_a_client_reads() -> set[str]:
    exposed = fields_each_model_exposes()
    methods: set[str] = set()
    for path in sorted(BACKEND.rglob("models/*.py")):
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for model in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
            served = exposed.get(model.name, set())
            if not served:
                continue
            for node in [n for n in ast.walk(model) if isinstance(n, ast.FunctionDef)]:
                parameters = {argument.arg for argument in node.args.args} - {"self"}
                if not parameters:
                    continue
                for statement in ast.walk(node):
                    if not isinstance(statement, ast.Assign):
                        continue
                    written = {
                        target.attr
                        for target in statement.targets
                        if isinstance(target, ast.Attribute)
                        and isinstance(target.value, ast.Name)
                        and target.value.id == "self"
                    }
                    if not written & served:
                        continue
                    if any(
                        isinstance(inner, ast.Name) and inner.id in parameters
                        for inner in ast.walk(statement.value)
                    ):
                        methods.add(node.name)
    return methods


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


def _handlers_in(scope: ast.AST) -> list[ast.ExceptHandler]:
    return [node for node in ast.walk(scope) if isinstance(node, ast.ExceptHandler) and node.name]


def _called_name(func: ast.AST) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _call_findings(scope, caught, tainted, subclasses, notes, helpers, relative) -> list[str]:
    findings: list[str] = []
    for statement in ast.walk(scope):
        if not isinstance(statement, ast.Call):
            continue
        arguments = list(statement.args) + [k.value for k in statement.keywords]
        if not any(
            _derives_from(argument, caught, tainted)
            and not any(_sanitised(inner) for inner in ast.walk(argument))
            for argument in arguments
        ):
            continue
        if isinstance(statement.func, ast.Name) and statement.func.id in subclasses:
            findings.append(
                f"{relative}:{statement.lineno} {statement.func.id}({caught}): {SERVES_EXCEPTION_TEXT}"
            )
        elif _called_name(statement.func) in helpers:
            findings.append(
                f"{relative}:{statement.lineno} {_called_name(statement.func)}({caught}): {SERVES_EXCEPTION_TEXT}"
            )
        elif isinstance(statement.func, ast.Attribute) and statement.func.attr in notes:
            receiver = f"{ast.unparse(statement.func.value)}.{statement.func.attr}"
            if receiver not in ALLOWED_NOTE_RECEIVERS:
                findings.append(
                    f"{relative}:{statement.lineno} {receiver}({caught}): {SERVES_EXCEPTION_TEXT_TO_A_FIELD}"
                )
    return findings


def findings_in(tree, subclasses, notes, helpers, relative) -> list[str]:
    findings: list[str] = []
    seen: set[str] = set()

    scopes = [tree] + [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    for scope in scopes:
        for handler in _handlers_in(scope):
            caught = handler.name
            tainted = _tainted_locals(handler, caught)
            # Inside the handler the caught name itself is live; the names assigned from
            # it are the ones that outlive it, because Python unbinds `as name` on exit.
            # A finding outside the handler is the same defect one statement later, and
            # #366's capital-increase site was exactly that shape.
            for finding in _call_findings(handler, caught, tainted, subclasses, notes, helpers, relative):
                if finding not in seen:
                    seen.add(finding)
                    findings.append(finding)
            if tainted and scope is not tree:
                for finding in _call_findings(scope, caught, tainted, subclasses, notes, helpers, relative):
                    if finding not in seen:
                        seen.add(finding)
                        findings.append(finding)
    return findings


def scan() -> tuple[list[str], int]:
    subclasses = api_exception_names()
    notes = note_methods_a_client_reads()
    helpers = helpers_that_build_an_exception(subclasses)
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
        findings += findings_in(tree, subclasses, notes, helpers, path.relative_to(ROOT))

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
        print(f"Caller-visible text built from an exception ({len(offenders)}):\n", file=sys.stderr)
        for finding in offenders:
            print(f"  {finding}", file=sys.stderr)
        for rule, explanation in RULES.items():
            if any(finding.endswith(rule) for finding in offenders):
                print(f"\n  {rule}: {explanation}", file=sys.stderr)
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

    print(f"No API error body and no client-read field carries an exception's text, in {checked} files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
