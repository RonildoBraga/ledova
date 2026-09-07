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

LEGACY: dict[str, int] = {
    "backend/companies/views/company.py:raw-orm-in-view": 1,
    "backend/tokens/views/trading_token.py:raw-orm-in-view": 1,
    "backend/users/views/notification_preferences.py:transaction-in-view": 1,
    "backend/users/views/user_preferences.py:transaction-in-view": 1,
}


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


def parents_of(tree: ast.AST) -> dict:
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
    return parents


def manager_accesses(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "objects":
            yield node


def receiver_of(node: ast.Attribute) -> str | None:
    value = node.value
    if isinstance(value, ast.Name):
        return value.id
    if isinstance(value, ast.Call):
        func = value.func
        # `type(self).objects` is the model reaching its own manager.
        if isinstance(func, ast.Name) and func.id == "type" and len(value.args) == 1:
            argument = value.args[0]
            return argument.id if isinstance(argument, ast.Name) else None
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            return func.attr
    return None


def names_scoped_in(scope: ast.AST, parents: dict) -> set[str]:
    # `queryset = Thing.objects.with_relations()` then `queryset.visible_to_user(...)`
    # scopes on the variable rather than in the chain. Collect the names that carry it.
    return {
        node.id
        for node in ast.walk(scope)
        if isinstance(node, ast.Name) and chain_is_scoped(node, parents)
    }


def scoped_objects_in(scope: ast.AST) -> set[str]:
    # `token = self.get_object()` puts a row the caller may already see into `token`.
    # Filtering another model by it carries that scoping, which is why four views
    # read `SecondModel.objects.for_thing(thing)` and are right to.
    names = set()
    for node in ast.walk(scope):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if names_in(node.value) & SCOPING_CALLS:
                names.add(node.targets[0].id)
    return names


def outermost_of(node: ast.AST, parents: dict) -> ast.AST:
    current = node
    while True:
        parent = parents.get(id(current))
        if isinstance(parent, ast.Attribute) or (isinstance(parent, ast.Call) and parent.func is current):
            current = parent
            continue
        return current


def assigned_name(node: ast.AST, parents: dict) -> str | None:
    current = node
    while True:
        parent = parents.get(id(current))
        if isinstance(parent, (ast.Attribute, ast.Call)):
            current = parent
            continue
        if isinstance(parent, ast.Assign) and len(parent.targets) == 1:
            target = parent.targets[0]
            return target.id if isinstance(target, ast.Name) else None
        return None


def chain_is_scoped(node: ast.AST, parents: dict) -> bool:
    current = node
    while True:
        parent = parents.get(id(current))
        if isinstance(parent, ast.Attribute):
            if parent.attr in SCOPING_CALLS:
                return True
            current = parent
        elif isinstance(parent, ast.Call) and parent.func is current:
            current = parent
        else:
            # A scoping call can also arrive as an argument, as in
            # `.filter(company__in=eligible_investor_companies(user))`. It is part of
            # this expression, so it scopes it - unlike a mention elsewhere in the
            # function, which is what the per-function check used to accept.
            return bool(names_in(current) & SCOPING_CALLS)


def guarded_by_action(node: ast.AST, parents: dict) -> bool:
    current = node
    while True:
        parent = parents.get(id(current))
        if parent is None:
            return False
        if isinstance(parent, ast.If) and current in parent.body and mentions_action(parent.test):
            return True
        current = parent


def mentions_action(test: ast.AST) -> bool:
    # `self.action` reads as an attribute; `getattr(self, "action", None)` as a string.
    if "action" in names_in(test):
        return True
    return any(
        isinstance(inner, ast.Constant) and inner.value == "action" for inner in ast.walk(test)
    )


def names_in(node: ast.AST) -> set[str]:
    return {inner.attr for inner in ast.walk(node) if isinstance(inner, ast.Attribute)} | {
        inner.id for inner in ast.walk(node) if isinstance(inner, ast.Name)
    }


def delegates_to_super(scope: ast.AST) -> bool:
    if len(scope.body) != 1:
        return False
    statement = scope.body[0]
    if not isinstance(statement, ast.Return) or not isinstance(statement.value, ast.Call):
        return False
    called = statement.value.func
    return (
        isinstance(called, ast.Attribute)
        and called.attr == scope.name
        and isinstance(called.value, ast.Call)
        and isinstance(called.value.func, ast.Name)
        and called.value.func.id == "super"
    )


def is_atomic(node: ast.AST) -> bool:
    chain = attribute_chain(node.func if isinstance(node, ast.Call) else node)
    return chain.endswith("transaction.atomic") or chain == "atomic"


def view_findings(tree: ast.AST):
    found = []
    decorating = set()
    parents = parents_of(tree)

    scopes = [tree] + [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    carried = {id(scope): names_scoped_in(scope, parents) for scope in scopes}
    scoped_rows = {id(scope): scoped_objects_in(scope) for scope in scopes}

    for scope in scopes:
        for node in manager_accesses(scope):
            if chain_is_scoped(node, parents):
                continue
            if assigned_name(node, parents) in carried[id(scope)]:
                continue
            if names_in(outermost_of(node, parents)) & scoped_rows[id(scope)]:
                continue
            found.append((node.lineno, VIEW_ORM))

    for scope in ast.walk(tree):
        if not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        for decorator in scope.decorator_list:
            if is_atomic(decorator) and scope.name in DRF_WRITE_HOOKS and delegates_to_super(scope):
                decorating.add(decorator.lineno)

        for node in ast.walk(scope):
            if not isinstance(node, ast.Attribute) or node.attr != "select_for_update":
                continue
            if scope.name != LOCKING_HOOK or not guarded_by_action(node, parents):
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

    if isinstance(node, ast.Attribute) and node.attr == "objects":
        receiver = receiver_of(node)
        if receiver is None or receiver not in owners:
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

    counts: dict[str, int] = {}
    lines: dict[str, list[str]] = {}
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
            counts[key] = counts.get(key, 0) + 1
            lines.setdefault(key, []).append(f"{relative}:{line}: {RULES[rule]}")

    grown = sorted(key for key, seen in counts.items() if seen > LEGACY.get(key, 0))
    stale = sorted(key for key, pinned in LEGACY.items() if counts.get(key, 0) < pinned)
    excused = sum(min(seen, LEGACY.get(key, 0)) for key, seen in counts.items())

    if arguments.show_legacy:
        for key in sorted(LEGACY):
            for entry in lines.get(key, []):
                print(entry)
        print(f"\n{excused} excused finding(s) across {len(LEGACY)} legacy entries.\n")

    if stale:
        print(f"These LEGACY counts are higher than what is there ({len(stale)}):\n", file=sys.stderr)
        for key in stale:
            print(f"  {key}: pinned {LEGACY[key]}, found {counts.get(key, 0)}", file=sys.stderr)
        print("\nLower the count in LEGACY, or delete the entry when it reaches zero.", file=sys.stderr)
        return 1

    if grown:
        print(f"Backend layer violations ({len(grown)} file/rule pairs):\n", file=sys.stderr)
        for key in grown:
            pinned = LEGACY.get(key, 0)
            print(f"  {key}: pinned {pinned}, found {counts[key]}", file=sys.stderr)
            for entry in lines[key]:
                print(f"    {entry}", file=sys.stderr)
        print(
            "\nThe layer that owns this is named in docs/ARCHITECTURE.md, "
            '"Backend layers".\nMove the logic rather than raising a LEGACY count: '
            "those only fall.",
            file=sys.stderr,
        )
        return 1

    print(f"Backend layers clean in {checked} files ({excused} known findings still in LEGACY).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
