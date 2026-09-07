#!/usr/bin/env python3
"""Fail when a test helper shadows a TestCase method the assertions depend on.

The rule and its scope are stated in docs/ARCHITECTURE.md under "The test
shadowing gate". This script is the mechanical half of that rule; keep the two
in step.

A test class that defines `def fail(self, ...)` replaces `TestCase.fail`, and
most of the assertion surface raises through it. Only the handful that call
`raise self.failureException` themselves survive: `_baseAssertEqual`, which is
why assertEqual on a scalar is always real, plus assertTrue and assertRegex.
Everything else builds its message and calls self.fail - so with fail shadowed
the message is built, the helper is called, and the assertion passes.

Measured, not assumed. Silent under a shadowed fail: assertEqual on a tuple,
list, dict, set or string; assertIn; assertNotIn; assertIsNone; assertIsInstance;
assertGreater; assertCountEqual. Still raising: assertEqual on a scalar,
assertTrue, assertRegex. That mixture is why the shadowing is invisible - the
suite keeps failing where you look and stops checking where you do not.

That happened here. `ReversingOnlyWhatWasDeductedTest.fail(tx_hash)` made six
tuple assertions inert across the file, and they were found only because a
deliberately reverted fix did not turn them red.

The rule refuses a test-class method whose name is a TestCase attribute, except
the documented override hooks - setUp, tearDown, their class forms,
setUpTestData and the runner protocol - which exist to be overridden. It is
decidable from the syntax alone: a method name compared against dir(TestCase).
"""

from __future__ import annotations

import argparse
import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"

OVERRIDABLE = frozenset(
    {
        "setUp",
        "tearDown",
        "setUpClass",
        "tearDownClass",
        "setUpTestData",
        "run",
        "debug",
        "countTestCases",
        "defaultTestResult",
        "shortDescription",
        "id",
    }
)

RESERVED = (
    frozenset(name for name in dir(unittest.TestCase) if not name.startswith("__"))
    - OVERRIDABLE
)

ALLOWED: dict[str, str] = {}


def is_test_file(path: Path) -> bool:
    parts = path.relative_to(BACKEND).parts
    return "tests" in parts or path.name.startswith("test_")


def shadowing(tree: ast.Module) -> list[tuple[int, str, str]]:
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for item in node.body:
            if (
                isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                and item.name in RESERVED
            ):
                found.append((item.lineno, node.name, item.name))
    return found


def scan() -> tuple[list[str], int]:
    findings = []
    checked = 0

    for path in sorted(BACKEND.rglob("*.py")):
        if not is_test_file(path):
            continue
        checked += 1
        relative = path.relative_to(ROOT)
        for lineno, class_name, method in shadowing(ast.parse(path.read_text())):
            key = f"{relative}:{class_name}.{method}"
            if key in ALLOWED:
                continue
            findings.append(
                f"{relative}:{lineno} {class_name}.{method} shadows unittest.TestCase.{method}"
            )

    return findings, checked


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--explain", action="store_true")
    arguments = parser.parse_args()

    if arguments.explain:
        print(f"Reserved names ({len(RESERVED)}): {', '.join(sorted(RESERVED))}")
        print(f"Override hooks ({len(OVERRIDABLE)}): {', '.join(sorted(OVERRIDABLE))}")
        return 0

    findings, checked = scan()

    if findings:
        print(
            f"Test helpers that shadow a TestCase method ({len(findings)}):\n",
            file=sys.stderr,
        )
        for finding in findings:
            print(f"  {finding}", file=sys.stderr)
        print(
            "\nMost assertions raise through TestCase.fail - assertEqual on a tuple, list, dict,"
            "\nset or string, and assertIn, assertIsNone, assertIsInstance, assertGreater among"
            "\nothers. A helper of the same name replaces it, so those assertions stop checking"
            "\nand keep passing. Rename the helper."
            '\n\nThe rule and its scope are in docs/ARCHITECTURE.md, "The test shadowing gate".',
            file=sys.stderr,
        )
        return 1

    print(f"No test helper shadows a TestCase method in {checked} test files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
