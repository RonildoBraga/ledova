#!/usr/bin/env python3
"""Fail on any comment or docstring in the source trees that carry none.

The rule, its scope and the list of permitted functional directives are stated
in docs/ARCHITECTURE.md under "Coding rules". This script is the mechanical
half of that rule; keep the two in step.
"""

from __future__ import annotations

import argparse
import ast
import io
import re
import sys
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PY = (".py",)
TS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
CSS = (".css",)
SOL = (".sol",)

# (path relative to the repository root, extensions checked, recurse into subdirectories)
TREES = (
    ("backend", PY + CSS, True),
    ("dashboard/src", TS + CSS, True),
    ("mobile/src", TS, True),
    ("mobile", TS, False),
    ("packages/shared", TS, True),
    ("packages/scripts", TS, True),
    ("marketing/src", TS + CSS, True),
    ("contracts/contracts", SOL, True),
    ("contracts/scripts", TS, True),
    ("contracts/test", TS, True),
)

SKIP_ANYWHERE = frozenset({".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", "__pycache__", "node_modules"})

SKIP_AT_TOP = frozenset(
    {
        ".expo",
        ".next",
        ".venv",
        "artifacts",
        "build",
        "cache",
        "coverage",
        "dist",
        "htmlcov",
        "media",
        "staticfiles",
        "typechain-types",
        "venv",
    }
)

PY_DIRECTIVE = re.compile(r"^(?:noqa|pragma|isort)\b|^(?:type|fmt)\s*:")
PY_CODING = re.compile(r"^#\s*(?:-\*-\s*)?coding[:=]\s*[-\w.]+\s*(?:-\*-)?\s*$")

TS_DIRECTIVE = re.compile(
    r"^(?:eslint-disable|eslint-enable|@ts-ignore|@ts-expect-error|@ts-nocheck"
    r"|prettier-ignore|@vitest-environment|@jest-environment|biome-ignore)\b"
    r"|^(?:istanbul|c8|v8)\s+ignore\b"
    r"|^global\s+[\w$]+(?:\s*[:,]\s*[\w$]+)*\s*$"
)
TS_REFERENCE = re.compile(r"^/\s*<reference\b")

SOL_DIRECTIVE = re.compile(r"^SPDX-License-Identifier\b")

DOCSTRING = "docstring or bare string statement"

IDENT_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_$")
ELEMENT_KEYWORDS = frozenset({"await", "case", "default", "return", "yield"})

REGEX_KEYWORDS = frozenset(
    {
        "await",
        "case",
        "delete",
        "do",
        "else",
        "in",
        "instanceof",
        "new",
        "of",
        "return",
        "throw",
        "typeof",
        "void",
        "yield",
    }
)


def render(text: str) -> str:
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= 110 else collapsed[:107] + "..."


def scan_c_like(
    text: str, *, line_comments: bool, templates: bool, regexes: bool, jsx: bool = False
) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    length = len(text)
    index = 0
    line = 1
    previous = ""
    previous_word = ""
    stack = [["code", 0]]

    def advance(count: int) -> None:
        nonlocal index, line
        stop = min(index + count, length)
        line += text.count("\n", index, stop)
        index = stop

    def regex_can_start() -> bool:
        if not previous:
            return True
        if previous_word:
            return previous_word in REGEX_KEYWORDS
        return previous not in ")]}\"'`<>"

    def element_can_start() -> bool:
        if index + 1 >= length:
            return False
        if text[index + 1] not in IDENT_CHARS and text[index + 1] not in ">/":
            return False
        if not previous:
            return True
        if previous_word:
            return previous_word in ELEMENT_KEYWORDS
        return previous in "=({[,;:?&|>}!+"

    while index < length:
        mode, depth = stack[-1]
        char = text[index]

        if mode == "jsx-text":
            if char == "{":
                stack.append(["code", 0])
                advance(1)
                previous, previous_word = "{", ""
                continue
            if char == "<":
                if text.startswith("</", index):
                    end = text.find(">", index)
                    end = length if end == -1 else end + 1
                    advance(end - index)
                    stack.pop()
                    previous, previous_word = ">", ""
                    continue
                stack.append(["jsx-tag", 0])
                advance(1)
                continue
            advance(1)
            continue

        if mode == "jsx-tag":
            if char in "'\"":
                cursor = text.find(char, index + 1)
                advance((length if cursor == -1 else cursor + 1) - index)
                continue
            if char == "{":
                stack.append(["code", 0])
                advance(1)
                previous, previous_word = "{", ""
                continue
            if text.startswith("/>", index):
                stack.pop()
                advance(2)
                previous, previous_word = ">", ""
                continue
            if char == ">":
                stack.pop()
                stack.append(["jsx-text", 0])
                advance(1)
                previous, previous_word = ">", ""
                continue
            advance(1)
            continue

        if mode == "template":
            if char == "\\":
                advance(2)
                continue
            if char == "`":
                stack.pop()
                advance(1)
                previous, previous_word = "`", ""
                continue
            if text.startswith("${", index):
                stack.append(["code", 0])
                advance(2)
                previous, previous_word = "{", ""
                continue
            advance(1)
            continue

        if char in " \t\r\n":
            advance(1)
            continue

        if char == "/" and index + 1 < length:
            following = text[index + 1]
            if line_comments and following == "/":
                end = text.find("\n", index)
                end = length if end == -1 else end
                found.append((line, text[index:end]))
                advance(end - index)
                previous, previous_word = "", ""
                continue
            if following == "*":
                end = text.find("*/", index + 2)
                end = length if end == -1 else end + 2
                found.append((line, text[index:end]))
                advance(end - index)
                previous, previous_word = "", ""
                continue
            if regexes and regex_can_start():
                cursor = index + 1
                in_class = False
                while cursor < length:
                    current = text[cursor]
                    if current == "\\":
                        cursor += 2
                        continue
                    if current == "\n":
                        break
                    if current == "[":
                        in_class = True
                    elif current == "]":
                        in_class = False
                    elif current == "/" and not in_class:
                        cursor += 1
                        break
                    cursor += 1
                advance(cursor - index)
                previous, previous_word = "/", ""
                continue

        if char in "'\"":
            cursor = index + 1
            while cursor < length:
                current = text[cursor]
                if current == "\\":
                    cursor += 2
                    continue
                if current in (char, "\n"):
                    cursor += 1
                    break
                cursor += 1
            advance(cursor - index)
            previous, previous_word = char, ""
            continue

        if templates and char == "`":
            stack.append(["template", 0])
            advance(1)
            previous, previous_word = "`", ""
            continue

        if jsx and char == "<" and element_can_start():
            stack.append(["jsx-tag", 0])
            advance(1)
            continue

        if char in IDENT_CHARS:
            cursor = index
            while cursor < length and text[cursor] in IDENT_CHARS:
                cursor += 1
            word = text[index:cursor]
            advance(cursor - index)
            previous, previous_word = word[-1], word
            continue

        if char == "{":
            stack[-1][1] = depth + 1
        elif char == "}":
            if depth > 0:
                stack[-1][1] = depth - 1
            elif len(stack) > 1:
                stack.pop()
                advance(1)
                previous, previous_word = "}", ""
                continue

        advance(1)
        previous, previous_word = char, ""

    return found


def body_of(text: str) -> str:
    if text.startswith("//"):
        return text[2:].strip()
    if text.startswith("/*"):
        inner = text[2:-2] if text.endswith("*/") else text[2:]
        lines = [line.strip().lstrip("*").strip() for line in inner.splitlines()]
        return next((line for line in lines if line), "")
    return text.strip()


def python_findings(text: str) -> list[tuple[int, str, bool]]:
    findings: list[tuple[int, str, bool]] = []
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError) as error:
        return [(0, f"could not tokenize: {error}", False)]

    for token in tokens:
        if token.type != tokenize.COMMENT:
            continue
        line = token.start[0]
        raw = token.string.strip()
        permitted = bool(
            (line == 1 and raw.startswith("#!"))
            or (line <= 2 and PY_CODING.search(raw))
            or PY_DIRECTIVE.match(raw.lstrip("#").strip())
        )
        findings.append((line, raw, permitted))

    try:
        tree = ast.parse(text)
    except SyntaxError as error:
        findings.append((0, f"could not parse: {error}", False))
        return findings

    for node in ast.walk(tree):
        for field in ("body", "orelse", "finalbody"):
            statements = getattr(node, field, None)
            if not isinstance(statements, list):
                continue
            for statement in statements:
                if (
                    isinstance(statement, ast.Expr)
                    and isinstance(statement.value, ast.Constant)
                    and isinstance(statement.value.value, str)
                ):
                    findings.append((statement.lineno, DOCSTRING, False))

    return sorted(set(findings))


def typescript_findings(text: str, jsx: bool = False) -> list[tuple[int, str, bool]]:
    findings = []
    for line, raw in scan_c_like(text, line_comments=True, templates=True, regexes=True, jsx=jsx):
        body = body_of(raw)
        permitted = bool(TS_REFERENCE.match(body) or TS_DIRECTIVE.match(body))
        findings.append((line, render(raw), permitted))
    return findings


def solidity_findings(text: str) -> list[tuple[int, str, bool]]:
    return [
        (line, render(raw), bool(SOL_DIRECTIVE.match(body_of(raw))))
        for line, raw in scan_c_like(text, line_comments=True, templates=False, regexes=False)
    ]


def css_findings(text: str) -> list[tuple[int, str, bool]]:
    return [
        (line, render(raw), False)
        for line, raw in scan_c_like(text, line_comments=False, templates=False, regexes=False)
    ]


FINDERS = {
    ".py": python_findings,
    ".css": css_findings,
    ".sol": solidity_findings,
}


def files_in(tree: str, extensions: tuple[str, ...], recurse: bool):
    base = ROOT / tree
    if not base.is_dir():
        return
    candidates = base.rglob("*") if recurse else base.iterdir()
    for path in sorted(candidates):
        if path.suffix not in extensions or not path.is_file():
            continue
        parts = path.relative_to(base).parts
        if any(part in SKIP_ANYWHERE for part in parts):
            continue
        if parts[:1] and parts[0] in SKIP_AT_TOP:
            continue
        yield path


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail on any comment or docstring in source.")
    parser.add_argument(
        "--show-allowed",
        action="store_true",
        help="also list the permitted functional directives that were found",
    )
    arguments = parser.parse_args()

    violations: list[str] = []
    allowed: list[str] = []
    checked = 0

    for tree, extensions, recurse in TREES:
        for path in files_in(tree, extensions, recurse):
            checked += 1
            relative = path.relative_to(ROOT)
            text = path.read_text(encoding="utf-8-sig", errors="replace")
            if path.suffix in FINDERS:
                results = FINDERS[path.suffix](text)
            else:
                results = typescript_findings(text, jsx=path.suffix in (".tsx", ".jsx"))
            for line, message, permitted in results:
                entry = f"{relative}:{line}: {message}"
                (allowed if permitted else violations).append(entry)

    if arguments.show_allowed:
        for entry in allowed:
            print(entry)
        print(f"\n{len(allowed)} permitted directive(s) in {checked} files.\n")

    if violations:
        print(f"Comments and docstrings are not permitted in source ({len(violations)} found):\n", file=sys.stderr)
        for entry in violations:
            print(f"  {entry}", file=sys.stderr)
        print(
            "\nNames and tests carry the meaning: rename the thing, or add a test."
            "\nThe rule, its scope and the permitted functional directives are in"
            '\ndocs/ARCHITECTURE.md, "Coding rules".',
            file=sys.stderr,
        )
        return 1

    print(f"No comments or docstrings in {checked} source files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
