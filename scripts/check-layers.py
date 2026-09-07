#!/usr/bin/env python3
"""Fail when a backend layer contains something the layer table forbids.

The layers, what each owns and what each never contains are stated in
docs/ARCHITECTURE.md under "Backend layers". This script is the mechanical half
of the "Never contains" column; keep the two in step.

Every offender that exists today is listed in LEGACY, so the gate is green on
the day it lands and blocks only new violations. LEGACY is the migration
backlog made visible: delete an entry when the file is cleaned, and the gate
holds the ground. An entry that no longer violates anything is reported as
stale, so the list cannot quietly outlive the problem.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"

SKIP_ANYWHERE = frozenset({"__pycache__", "migrations", "tests", ".git", "node_modules"})

SCOPING_CALLS = frozenset(
    {
        "visible_to_user",
        "manageable_by_user",
        "none",
        "get_object",
        "get_queryset",
        "eligible_investor_companies",
        "investor_eligibility",
    }
)

LOCKING_HOOK = "get_queryset"
DRF_WRITE_HOOKS = frozenset({"update", "partial_update", "create", "destroy"})

OWN_MANAGER_RECEIVERS = frozenset({"cls", "self"})

VIEW_ORM = "raw-orm-in-view"
VIEW_TRANSACTION = "transaction-in-view"
VIEW_LOCK = "select-for-update-in-view"
VIEW_LOGGER = "logger-in-view"
MODEL_QUERY = "query-in-model"
TASK_TRANSACTION = "transaction-in-task"

RULES = {
    VIEW_ORM: "views reach the ORM only through visible_to_user or manageable_by_user",
    VIEW_TRANSACTION: "a transaction the view opens around its own logic is a workflow; move it to a service",
    VIEW_LOCK: "select_for_update outside get_queryset means the view is orchestrating; move it to a service",
    VIEW_LOGGER: "log in services and tasks, not in views",
    MODEL_QUERY: "a model queries its own manager only; another model's manager belongs in a queryset or a service",
    TASK_TRANSACTION: "a task loads a row and calls one service; the service owns the transaction",
}

LEGACY = frozenset(
    {
        "backend/authentication/views/user.py:raw-orm-in-view",
    }
)


def layer_of(path: Path) -> str | None:
    parts = path.relative_to(BACKEND).parts
    for index, part in enumerate(parts):
        if part in ("views", "models", "tasks"):
            return part
        if index == 1 and part in ("views.py", "models.py", "tasks.py"):
            return part[:-3]
    return None


def python_files():
    for path in sorted(BACKEND.rglob("*.py")):
        if any(part in SKIP_ANYWHERE for part in path.relative_to(BACKEND).parts):
            continue
        layer = layer_of(path)
        if layer is not None:
            yield path, layer


def attribute_chain(node: ast.AST) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def names_in(node: ast.AST) -> set[str]:
    return {inner.attr for inner in ast.walk(node) if isinstance(inner, ast.Attribute)} | {
        inner.id for inner in ast.walk(node) if isinstance(inner, ast.Name)
    }


def unscoped_orm_lines(scope: ast.AST) -> list[int]:
    if names_in(scope) & SCOPING_CALLS:
        return []
    return [
        node.lineno
        for node in ast.walk(scope)
        if isinstance(node, ast.Attribute) and node.attr == "objects" and isinstance(node.value, ast.Name)
    ]


def is_atomic(node: ast.AST) -> bool:
    chain = attribute_chain(node.func if isinstance(node, ast.Call) else node)
    return chain.endswith("transaction.atomic") or chain == "atomic"


def view_findings(tree: ast.AST):
    found = []
    decorating = set()

    for scope in ast.walk(tree):
        if not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        found.extend((line, VIEW_ORM) for line in unscoped_orm_lines(scope))

        for decorator in scope.decorator_list:
            if is_atomic(decorator) and scope.name in DRF_WRITE_HOOKS:
                decorating.add(decorator.lineno)

        for node in ast.walk(scope):
            if isinstance(node, ast.Attribute) and node.attr == "select_for_update" and scope.name != LOCKING_HOOK:
                found.append((node.lineno, VIEW_LOCK))

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if is_atomic(node) and node.lineno not in decorating:
                found.append((node.lineno, VIEW_TRANSACTION))
            if attribute_chain(node).endswith("logging.getLogger"):
                found.append((node.lineno, VIEW_LOGGER))

    return sorted(set(found))


def model_findings(node: ast.AST, owners: frozenset[str] = OWN_MANAGER_RECEIVERS):
    found = []

    for child in ast.iter_child_nodes(node):
        inherited = owners | {child.name} if isinstance(child, ast.ClassDef) else owners
        found.extend(model_findings(child, inherited))

    if isinstance(node, ast.Attribute):
        chain = attribute_chain(node)
        if ".objects." in chain and chain.split(".", 1)[0] not in owners:
            found.append((node.lineno, MODEL_QUERY))

    return found


def findings_for(tree: ast.AST, layer: str):
    found = []

    if layer == "views":
        found.extend(view_findings(tree))

    if layer == "models":
        found.extend(model_findings(tree))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        chain = attribute_chain(node)

        if layer == "tasks" and (chain.endswith("transaction.atomic") or chain == "atomic"):
            found.append((node.lineno, TASK_TRANSACTION))

    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--show-legacy", action="store_true")
    arguments = parser.parse_args()

    violations: list[str] = []
    excused: list[str] = []
    seen_keys: set[str] = set()
    checked = 0

    for path, layer in python_files():
        checked += 1
        relative = path.relative_to(ROOT)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig", errors="replace"))
        except SyntaxError as error:
            print(f"{relative}: could not parse: {error}", file=sys.stderr)
            return 1

        for line, rule in findings_for(tree, layer):
            key = f"{relative}:{rule}"
            seen_keys.add(key)
            entry = f"{relative}:{line}: {RULES[rule]}"
            (excused if key in LEGACY else violations).append(entry)

    stale = sorted(LEGACY - seen_keys)

    if arguments.show_legacy:
        for entry in sorted(excused):
            print(entry)
        print(f"\n{len(excused)} excused finding(s) across {len(LEGACY)} legacy entries.\n")

    if stale:
        print(f"These LEGACY entries no longer violate anything ({len(stale)}):\n", file=sys.stderr)
        for key in stale:
            print(f"  {key}", file=sys.stderr)
        print("\nDelete them from LEGACY in scripts/check-layers.py.", file=sys.stderr)
        return 1

    if violations:
        print(f"Backend layer violations ({len(violations)}):\n", file=sys.stderr)
        for entry in violations:
            print(f"  {entry}", file=sys.stderr)
        print(
            "\nThe layer that owns this is named in docs/ARCHITECTURE.md, "
            '"Backend layers".\nMove the logic rather than adding to LEGACY: '
            "that list only shrinks.",
            file=sys.stderr,
        )
        return 1

    print(f"Backend layers clean in {checked} files ({len(excused)} known findings still in LEGACY).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
