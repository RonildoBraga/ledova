#!/usr/bin/env python3
"""Fail when non-test, non-migration code binds a transaction or a cursor to the default connection.

`transaction.atomic()` binds to DEFAULT_DB_ALIAS at decoration time; the router sends the
queries to `current_alias()` at execution time. They agree only when the ambient alias *is*
`default`, which is what the ordinary test settings pin - so a mismatch is green in CI and
either raises or silently autocommits in production. Measured on 2026-09-07: under
RLS_AMBIENT_ALIAS=app a row written inside a failed `atomic()` block survives it.

`django.db.connection` is always the default connection, which under R1 is the role with
BYPASSRLS, so a raw read through it is a policy bypass as well as a transaction problem.
There is no such site today; this keeps it that way.

The remedy is `shared.db.atomic`, `shared.db.on_commit` and `connections[alias]`. R23 on
#115, from #378.
"""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
SKIP_ANYWHERE = frozenset({"__pycache__", "migrations", "tests", ".git", "node_modules"})

BOUND_TO_DEFAULT = {
    "transaction.atomic": "shared.db.atomic",
    "transaction.on_commit": "shared.db.on_commit",
    "connection.cursor": "connections[current_alias()].cursor",
}

# These reach for a connection deliberately and already name which one, so the rule they
# would otherwise break is the rule they implement.
ALLOWED = {
    "backend/shared/db/transactions.py": "the helper itself; it is what everything else calls",
    "backend/shared/db/principal.py": "takes connections[alias or current_alias()] explicitly",
    "backend/shared/management/commands/check_rls_roles.py": "asks each alias in turn, by name, on purpose",
}


def dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Attribute):
        return f"{dotted(node.value)}.{node.attr}"
    if isinstance(node, ast.Name):
        return node.id
    return ""


def findings_for(tree: ast.AST) -> list[tuple[int, str]]:
    found = []
    for node in ast.walk(tree):
        called = None
        if isinstance(node, ast.Call):
            called = dotted(node.func)
        elif isinstance(node, ast.Attribute):
            called = dotted(node)
        if called in BOUND_TO_DEFAULT:
            found.append((node.lineno, called))
    return sorted(set(found))


def files() -> list[Path]:
    return sorted(
        path
        for path in BACKEND.rglob("*.py")
        if not SKIP_ANYWHERE & set(path.relative_to(BACKEND).parts)
    )


def main() -> int:
    findings: list[str] = []
    checked = 0
    for path in files():
        relative = str(path.relative_to(ROOT))
        if relative in ALLOWED:
            continue
        checked += 1
        for line, called in findings_for(ast.parse(path.read_text())):
            findings.append(f"{relative}:{line}: {called} binds to the default connection, not {BOUND_TO_DEFAULT[called]}")

    stale = sorted(name for name in ALLOWED if not (ROOT / name).is_file())
    if stale:
        findings.extend(f"{name}: allowed, and the file is gone" for name in stale)

    if findings:
        print(
            "These bind a transaction or a cursor to the default connection while the router "
            f"sends the queries elsewhere ({len(findings)}):\n  " + "\n  ".join(findings),
            file=sys.stderr,
        )
        print("\nUse shared.db.atomic, shared.db.on_commit, or connections[alias]. R23, from #378.", file=sys.stderr)
        return 1

    print(f"No transaction or cursor is bound to the default connection, in {checked} source files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
