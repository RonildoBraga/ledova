#!/usr/bin/env python3
"""Fail when a workspace's type-check script would examine no files.

A solution-style tsconfig - `"files": []` with `references` - delegates the real
configuration to the referenced projects. `tsc --noEmit` does not follow project
references, so against such a config it type-checks nothing and exits 0. The
script reads as a type-check, CI reads as green, and every type error in that
workspace passes.

`tsc -b` (build mode) does follow references, so the rule is: a workspace whose
tsconfig examines no files of its own must type-check in build mode. `make check`
runs this and CI runs it beside the other source gates.

What counts as examining no files is decided by TypeScript, not by the presence
of one key. Verified against tsc by type-checking a file with a known error under
each shape:

    {"files": []}                            examines nothing
    {"files": [], "include": []}             examines nothing
    {"include": []}                          examines nothing
    {"references": [...]}                    examines everything (include defaults to **/*)
    {"files": [], "include": ["**/*"]}       examines everything
    {"extends": <base with "files": []>}     examines nothing

The last is why `extends` has to be resolved rather than read past: `tsc
--showConfig` does not print the inherited `files`, but the inheritance is real,
and a workspace whose base carries the empty `files` is exactly as unchecked as
one that carries it directly. The chain is consulted only when a config declares
neither `files` nor `include` itself, because a local one overwrites the base's.

An `extends` that cannot be resolved is reported rather than skipped. The gate
answering "nothing found" because it could not read the file is the failure this
rule exists to prevent, one level up.

A workspace in WORKSPACES with no `type-check` script, no `package.json` or no
`tsconfig.json` is reported for the same reason. The gate knows how many
workspaces it expects, so a workspace falling out of its coverage is something it
can see - and the only other signal was a smaller number inside a green success
line, which nobody diffs between runs.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKSPACES = ("dashboard", "marketing", "mobile", "packages/shared")
BUILD_MODE = re.compile(r"(^|\s)(-b|--build)(\s|$)")
LINE_COMMENT = re.compile(r"(^|\s)//.*$", re.MULTILINE)
BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
TRAILING_COMMA = re.compile(r",(\s*[}\]])")


class Unreadable(Exception):
    """A tsconfig the gate cannot parse or an extends it cannot follow."""


def parse_jsonc(path: Path) -> dict:
    """tsconfig.json is JSONC: block comments and trailing commas are legal."""
    text = path.read_text()
    text = BLOCK_COMMENT.sub("", text)
    text = LINE_COMMENT.sub("", text)
    text = TRAILING_COMMA.sub(r"\1", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise Unreadable(f"{path.relative_to(ROOT)} is not valid JSONC: {error}") from error


def resolve_extends(specifier: str, source: Path) -> Path:
    if specifier.startswith(".") or specifier.startswith("/"):
        candidates = [source.parent / specifier, source.parent / f"{specifier}.json"]
    else:
        candidates = []
        for parent in [source.parent, *source.parents]:
            modules = parent / "node_modules"
            candidates += [
                modules / specifier,
                modules / f"{specifier}.json",
                modules / specifier / "tsconfig.json",
            ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise Unreadable(
        f"{source.relative_to(ROOT)} extends {specifier!r}, which this gate cannot find. "
        "Install the workspace, or state the file set locally."
    )


def declared_file_set(path: Path, seen: tuple[Path, ...] = ()) -> dict:
    """Merge "files" and "include" down the extends chain, last declaration winning.

    Each key is resolved independently: a base declaring "files" does not suppress
    an "include" declared elsewhere in the chain. Measured against tsc 5.9.3 - a
    config extending ["<include: src>", "<files: []>"] type-checks src in either
    order, so the two keys cannot be carried as a pair.
    """
    if path in seen:
        raise Unreadable(f"{path.relative_to(ROOT)} extends itself in a cycle.")

    config = parse_jsonc(path)
    declared: dict = {}

    specifiers = config.get("extends") or []
    if isinstance(specifiers, str):
        specifiers = [specifiers]

    needs_base = "files" not in config or "include" not in config
    if specifiers and needs_base:
        for specifier in specifiers:
            declared.update(declared_file_set(resolve_extends(specifier, path), seen + (path,)))

    for key in ("files", "include"):
        if key in config:
            declared[key] = config[key]
    return declared


def examines_nothing(path: Path) -> bool:
    local = parse_jsonc(path)
    if local.get("include") or local.get("files"):
        # A non-empty local file set settles it; the base cannot take files away.
        return False

    declared = declared_file_set(path)
    files = declared.get("files") or []
    if "include" in declared:
        include = declared["include"] or []
    else:
        # TypeScript defaults include to everything, but only when neither key appears.
        include = [] if "files" in declared else ["**/*"]
    return not files and not include


def main() -> int:
    failures: list[str] = []
    checked = 0

    for name in WORKSPACES:
        manifest = ROOT / name / "package.json"
        tsconfig = ROOT / name / "tsconfig.json"
        missing = [p.name for p in (manifest, tsconfig) if not p.exists()]
        if missing:
            failures.append(f"{name}: listed in WORKSPACES but has no {' and no '.join(missing)}.")
            continue

        script = json.loads(manifest.read_text()).get("scripts", {}).get("type-check")
        if script is None:
            failures.append(
                f"{name}: listed in WORKSPACES but declares no type-check script, so this gate "
                "checks nothing there. Add one, or remove the workspace from WORKSPACES."
            )
            continue

        checked += 1
        try:
            hollow = examines_nothing(tsconfig)
        except Unreadable as error:
            failures.append(f"{name}: {error}")
            continue

        if not hollow:
            continue
        if BUILD_MODE.search(script):
            continue
        if parse_jsonc(tsconfig).get("references"):
            failures.append(
                f"{name}: tsconfig.json examines no files of its own and delegates to references, "
                f"so `{script}` checks nothing. Use `tsc -b --noEmit`."
            )
        else:
            failures.append(
                f"{name}: tsconfig.json examines no files and references no project, "
                f"so `{script}` checks nothing and build mode would not help. "
                "Give it a file set."
            )

    if failures:
        print(f"Workspaces whose type-check does not check them ({len(failures)}):\n", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1

    print(f"Type-check scripts reach their files in {checked} workspaces.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
