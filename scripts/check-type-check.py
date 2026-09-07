#!/usr/bin/env python3
"""Fail when a workspace's type-check script would examine no files.

A solution-style tsconfig - `"files": []` with `references` - delegates the real
configuration to the referenced projects. `tsc --noEmit` does not follow project
references, so against such a config it type-checks nothing and exits 0. The
script reads as a type-check, CI reads as green, and every type error in that
workspace passes.

`tsc -b` (build mode) does follow references, so the rule is: a workspace whose
tsconfig delegates must type-check in build mode. `make check` runs this and CI
runs it beside the other source gates.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKSPACES = ("dashboard", "marketing", "mobile", "packages/shared")
BUILD_MODE = re.compile(r"(^|\s)(-b|--build)(\s|$)")


def strip_comments(text: str) -> str:
    return re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)


def delegates_to_references(config: dict) -> bool:
    return config.get("files") == [] and bool(config.get("references")) and "include" not in config


def main() -> int:
    failures = []
    checked = 0

    for name in WORKSPACES:
        manifest = ROOT / name / "package.json"
        tsconfig = ROOT / name / "tsconfig.json"
        if not manifest.exists() or not tsconfig.exists():
            continue

        script = json.loads(manifest.read_text()).get("scripts", {}).get("type-check")
        if script is None:
            continue

        checked += 1
        config = json.loads(strip_comments(tsconfig.read_text()))
        if delegates_to_references(config) and not BUILD_MODE.search(script):
            failures.append(
                f"{name}: tsconfig.json delegates to references, so `{script}` checks no files. "
                "Use `tsc -b --noEmit`."
            )

    if failures:
        print(f"Type-check scripts that examine nothing ({len(failures)}):\n", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1

    print(f"Type-check scripts reach their files in {checked} workspaces.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
