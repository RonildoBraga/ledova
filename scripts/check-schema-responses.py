#!/usr/bin/env python3
"""Fail when a view returns a serializer the generated schema does not know about.

The rule and its scope are stated in docs/GATES.md under "The schema
response gate". This script is the mechanical half of that rule; keep the two in
step.

drf-spectacular infers an operation's response from `get_serializer_class()`. A
view that builds its own `Response` with a different serializer is documented as
returning the wrong shape, and every consumer that trusts the schema inherits the
error - including the API type drift gate, which cannot tell a schema defect from
a type defect and would record the former as the latter.

So: a view method that returns `Response(XSerializer(...).data)`, or a dict whose
values include one, must carry an `@extend_schema` naming the shape it actually
returns. Naming it is enough; the gate does not verify that the declaration is
accurate, because that is not decidable from syntax. What it decides is that
somebody stated something, which is the difference between a wrong answer and no
answer.

The rule is deliberately narrow. `Response(serializer.data)` where `serializer`
came from `self.get_serializer(...)` is exactly what the generator already
infers, so it is not a finding. Neither is a bare `Response(some_dict)` - that
shape says nothing about a serializer and is covered by the second rule below.

Second rule: an action that declares no serializer the generator can find must
say so. `@extend_schema(responses=...)` states the shape; `@extend_schema(exclude=True)`
states that the endpoint is deliberately absent, which a provider-facing webhook
is. Either is an answer; silence is what leaves a hole in the schema shaped
exactly like an endpoint that does not exist.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"

# ast.AsyncFunctionDef is not a subclass of ast.FunctionDef, so walking only the
# latter makes every async view method invisible to every rule below.
DEFINITIONS = (ast.FunctionDef, ast.AsyncFunctionDef)

HAND_BUILT = "hand-built-response"
UNDECLARED = "undeclared-action"
INERT = "inert-declaration"

RULES = {
    HAND_BUILT: (
        "returns a serializer the generator does not infer, so the schema documents the wrong "
        "shape. Add @extend_schema(responses=...) naming what it returns."
    ),
    UNDECLARED: (
        "is an action the generator cannot find a serializer for, so it is missing from the "
        "schema entirely. Add @extend_schema(responses=...), or exclude=True if it is "
        "deliberately absent."
    ),
    INERT: (
        "carries @extend_schema below @action, where it has no effect. Decorators apply "
        "bottom-up and drf-spectacular reads the outermost, so @extend_schema must sit "
        "above @action."
    ),
}

# Each entry is one category with a fix, not a count with a history: these actions
# build their body with a ** spread, so which fields cross the layer is not
# decidable from the source. Lowering an entry means giving that action a written
# shape - by hand, because the spread is why it cannot be read off. A count that
# only falls is a ratchet; a count with no stated way down is a hiding place.
LEGACY: dict[str, int] = {
    "backend/assets/views/asset.py:undeclared-action": 1,
    "backend/portfolios/views/portfolio.py:undeclared-action": 2,
    "backend/tokens/views/trading_order.py:undeclared-action": 2,
    "backend/tokens/views/trading_transfer.py:undeclared-action": 2,
    "backend/users/views/notification.py:undeclared-action": 2,
    "backend/users/views/user_profile.py:undeclared-action": 1,
}


def decorator_names(node: ast.AST) -> list[str]:
    names = []
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        names.append(ast.unparse(target))
    return names


def declares_schema(node: ast.AST) -> bool:
    """An @extend_schema that names neither responses nor exclude says nothing about the body."""
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        target = ast.unparse(decorator.func)
        if "extend_schema" not in target:
            continue
        if any(keyword.arg in ("responses", "exclude") for keyword in decorator.keywords):
            return True
    return False


def declaration_is_inert(node: ast.AST) -> bool:
    """@extend_schema below @action is applied first and then wrapped away.

    Decorators apply bottom-up, and drf-spectacular reads the annotation off the
    outermost object. An @extend_schema under an @action is therefore silently
    ignored: the schema keeps whatever get_serializer_class would have given it,
    which is exactly the wrong shape this gate exists to refuse. It reads as a
    declaration and is not one, so it is worse than no declaration at all.
    """
    names = decorator_names(node)
    schema = next((i for i, name in enumerate(names) if "extend_schema" in name), None)
    action = next((i for i, name in enumerate(names) if name.endswith("action")), None)
    return schema is not None and action is not None and action < schema


def is_action(node: ast.AST) -> bool:
    return any(name.endswith("action") for name in decorator_names(node))


def _locals_holding_serializers(node: ast.AST) -> dict[str, str]:
    """Local names assigned a serializer instance, so `x = S(...)` then `Response(x.data)` is seen."""
    held: dict[str, str] = {}
    for statement in ast.walk(node):
        if not isinstance(statement, ast.Assign) or not isinstance(statement.value, ast.Call):
            continue
        called = statement.value.func
        if not isinstance(called, ast.Name) or not called.id.endswith("Serializer"):
            continue
        for target in statement.targets:
            if isinstance(target, ast.Name):
                held[target.id] = called.id
    return held


def serializers_returned(node: ast.AST) -> set[str]:
    """Serializer classes a Response(...) in this method renders.

    Both spellings count: instantiated inside the call, and instantiated into a
    local first. The second is not a rarer shape - CompanyViewSet.create uses it -
    and a gate that only sees the first reports the tidier code and misses the
    other.
    """
    found: set[str] = set()
    held = _locals_holding_serializers(node)

    for statement in ast.walk(node):
        if not isinstance(statement, ast.Call):
            continue
        if not isinstance(statement.func, ast.Name) or statement.func.id != "Response":
            continue
        for inner in ast.walk(statement):
            if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name):
                if inner.func.id.endswith("Serializer"):
                    found.add(inner.func.id)
            elif isinstance(inner, ast.Attribute) and isinstance(inner.value, ast.Name):
                serializer = held.get(inner.value.id)
                if serializer and inner.attr == "data":
                    found.add(serializer)
    return found


def _successful(call: ast.Call) -> bool:
    """A Response(...) with no status, or a 2xx one. Error paths are not the contract."""
    for keyword in call.keywords:
        if keyword.arg != "status":
            continue
        source = ast.unparse(keyword.value)
        named = re.search(r"HTTP_(\d)", source)
        if named:
            return named.group(1) == "2"
        if source.isdigit():
            return source.startswith("2")
        # A status the gate cannot read is not evidence the path is an error path,
        # so it counts as the contract and is reported rather than skipped.
        return True
    return True


def builds_a_dict(node: ast.AST) -> bool:
    """Returns a literal dict the generator cannot infer from a serializer."""
    for statement in ast.walk(node):
        if not isinstance(statement, ast.Call):
            continue
        if not isinstance(statement.func, ast.Name) or statement.func.id != "Response":
            continue
        if not statement.args or not _successful(statement):
            continue
        if isinstance(statement.args[0], ast.Dict) and statement.args[0].keys:
            return True
    return False


def helpers_called(node: ast.AST) -> set[str]:
    """Names of self._helper() calls made by this method."""
    called = set()
    for inner in ast.walk(node):
        if (
            isinstance(inner, ast.Call)
            and isinstance(inner.func, ast.Attribute)
            and isinstance(inner.func.value, ast.Name)
            and inner.func.value.id == "self"
            and inner.func.attr.startswith("_")
        ):
            called.add(inner.func.attr)
    return called


def scan() -> tuple[list[str], int]:
    findings: list[str] = []
    checked = 0

    for path in sorted(BACKEND.rglob("*.py")):
        parts = path.relative_to(BACKEND).parts
        if "views" not in parts and path.name != "views.py":
            continue
        if "tests" in parts or "migrations" in parts:
            continue

        checked += 1
        tree = ast.parse(path.read_text())
        relative = path.relative_to(ROOT)

        methods = [n for n in ast.walk(tree) if isinstance(n, DEFINITIONS)]
        by_name = {n.name: n for n in methods}

        for node in methods:
            if declaration_is_inert(node):
                findings.append(f"{relative}:{node.lineno} {node.name}: {INERT}")
                continue
            if node.name.startswith("_"):
                # A private helper serves no route. What it returns is attributed
                # to the routable methods that call it, which are what the schema
                # documents.
                continue
            if declares_schema(node):
                continue
            returned = set(serializers_returned(node))
            for helper in helpers_called(node):
                target = by_name.get(helper)
                if target is not None:
                    returned |= serializers_returned(target)
            if returned:
                findings.append(
                    f"{relative}:{node.lineno} {node.name} returns "
                    f"{', '.join(sorted(returned))}: {HAND_BUILT}"
                )
                continue

            builds = builds_a_dict(node) or any(
                builds_a_dict(by_name[helper]) for helper in helpers_called(node) if helper in by_name
            )
            if builds and is_action(node):
                findings.append(
                    f"{relative}:{node.lineno} {node.name} returns a literal body: {UNDECLARED}"
                )

    return findings, checked


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--explain", action="store_true")
    arguments = parser.parse_args()

    if arguments.explain:
        for rule, explanation in RULES.items():
            print(f"{rule}: {explanation}")
        return 0

    findings, checked = scan()

    counts: dict[str, int] = {}
    for finding in findings:
        key = finding.split(" ")[0].rsplit(":", 1)[0] + ":" + finding.rsplit(": ", 1)[1]
        counts[key] = counts.get(key, 0) + 1

    allowed_counts = dict(LEGACY)
    new = {key: count for key, count in counts.items() if count > allowed_counts.get(key, 0)}
    stale = sorted(key for key, pinned in allowed_counts.items() if counts.get(key, 0) < pinned)

    if new:
        offenders = [f for f in findings if f.split(" ")[0].rsplit(":", 1)[0] + ":" + f.rsplit(": ", 1)[1] in new]
        print(f"Views whose response the schema does not know ({len(offenders)}):\n", file=sys.stderr)
        for finding in offenders:
            print(f"  {finding}", file=sys.stderr)
        print("", file=sys.stderr)
        for rule in sorted({finding.rsplit(": ", 1)[1] for finding in offenders}):
            print(f"  {rule}: {RULES[rule]}", file=sys.stderr)
        print(
            '\nThe rule and its scope are in docs/GATES.md, "The schema response gate".',
            file=sys.stderr,
        )
        return 1

    if stale:
        print(f"These pinned counts are higher than what is there ({len(stale)}):\n", file=sys.stderr)
        for key in stale:
            print(f"  {key}: pinned {allowed_counts[key]}, found {counts.get(key, 0)}", file=sys.stderr)
        return 1

    print(
        f"Every view response the schema documents is one a view states, in {checked} files "
        f"({sum(LEGACY.values())} literal bodies still in LEGACY)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
