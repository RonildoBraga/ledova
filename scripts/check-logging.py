#!/usr/bin/env python3
"""Fail when a log line is shaped so that it can carry a credential or an email address.

The rule and its scope are stated in docs/GATES.md under "The logging
privacy gate". This script is the mechanical half of that rule; keep the two in
step.

Two rules, each chosen because it is decidable from the syntax alone rather
than from what a value happens to hold at run time.

Clients: every argument of a console call must be a single string literal or a
single template literal. Passing an object hands the console the whole object,
and an AxiosError's object graph includes config.data, the serialised request
body -- the password on a failed sign-in. A template literal cannot leak it:
String(error) is the error's message, never its request. JSON.stringify inside
one is the way back out, so it is refused there too.

Backend: no logging call may reference an email address, a password or a push
token. "Reference" means an expression whose own syntax names one: an attribute
access, a bare name, or a constant string subscript. A user's primary key
identifies them for an operator without putting an email in a log aggregator.

Backend, second rule: no logging call may hand a whole provider response body to
the formatter. A named field is a decision about what an operator needs; a whole
body is whatever the provider chose to send, and for a KYC provider that is the
applicant dossier - legal name, date of birth, residential address, document
number, email address. The syntax that says "whole body" is a bare name from
BODY_NAMES, a `.text` / `.content` / `.data` / `.details` attribute, a `.json()`
call, or a constant subscript or `.get()` of one of those keys, reached directly
or through str(), repr(), json.dumps() or .format().
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")

CLIENT_TREES = ("dashboard/src", "mobile/src", "packages/shared/src", "marketing/src")
BACKEND_TREE = "backend"

SKIP_ANYWHERE = frozenset({".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", "__pycache__", "node_modules"})
SKIP_AT_TOP = frozenset({".expo", ".next", ".venv", "build", "coverage", "dist", "htmlcov", "media", "staticfiles", "venv"})

CONSOLE_ARGUMENT = "console-argument-is-not-a-literal"
CONSOLE_STRINGIFY = "console-argument-stringifies-an-object"
CONSOLE_BODY = "console-argument-interpolates-a-request-or-response-body"
LOG_PRIVATE = "private-value-in-a-log-line"
LOG_BODY = "provider-body-in-a-log-line"
LOG_ALIAS = "logger-bound-to-a-name-the-gate-does-not-scan"

RULES = {
    CONSOLE_ARGUMENT: "a console argument must be a string literal or a template literal, never an object",
    CONSOLE_STRINGIFY: "JSON.stringify inside a console argument serialises the object the literal was meant to keep out",
    CONSOLE_BODY: "a template literal that interpolates a request or response body prints what the literal was meant to keep out",
    LOG_PRIVATE: "log an identifier an operator can resolve, never an email address, a password or a push token",
    LOG_BODY: "log the fields an operator needs, never a whole provider response body",
    LOG_ALIAS: "bind a logger to logger, log or logging; any other name is not scanned by this gate",
}

CONSOLE_METHODS = frozenset({"assert", "debug", "dir", "error", "info", "log", "table", "trace", "warn"})

LOG_OBJECTS = frozenset({"logger", "logging", "log"})
LOG_METHODS = frozenset({"critical", "debug", "error", "exception", "fatal", "info", "log", "warn", "warning"})
PRIVATE_NAMES = frozenset({"email", "password", "push_token"})

BODY_NAMES = frozenset(
    {
        "applicant_data",
        "body",
        "content",
        "data",
        "error_body",
        "error_data",
        "payload",
        "raw",
        "resp",
        "response",
        "response_data",
        "result",
        "status_data",
        "webhook_data",
    }
)
BODY_ATTRIBUTES = frozenset({"body", "content", "data", "details", "text"})
BODY_KEYS = frozenset({"body", "content", "data", "details", "payload", "raw", "response", "result"})
SUB_BODY_KEYS = frozenset(
    {
        "applicant",
        "applicantData",
        "applicant_data",
        "addresses",
        "fixedInfo",
        "fixed_info",
        "idDocs",
        "id_docs",
        "info",
        "review",
        "reviewResult",
        "review_result",
    }
)
DOCUMENT_KEYS = BODY_KEYS | SUB_BODY_KEYS
STRINGIFIERS = frozenset({"dumps", "format", "pformat", "pprint", "repr", "str"})

IDENT_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_$")
REGEX_KEYWORDS = frozenset(
    {"await", "case", "delete", "do", "else", "in", "instanceof", "new", "of", "return", "throw", "typeof", "void", "yield"}
)
OPENERS = {"(": ")", "[": "]", "{": "}"}
CLOSERS = frozenset(")]}")


def render(text: str) -> str:
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= 90 else collapsed[:87] + "..."


def tokenize_script(text: str) -> list[tuple[str, str, int]]:
    tokens: list[tuple[str, str, int]] = []
    length = len(text)
    index = 0
    line = 1

    def previous_token() -> tuple[str, str, int] | None:
        return tokens[-1] if tokens else None

    def regex_can_start() -> bool:
        token = previous_token()
        if token is None:
            return True
        kind, body, _ = token
        if kind == "word":
            return body in REGEX_KEYWORDS
        if kind in ("string", "template", "regex"):
            return False
        return body not in ")]}"

    def emit(kind: str, start: int, stop: int) -> None:
        nonlocal index, line
        body = text[start:stop]
        tokens.append((kind, body, line))
        line += body.count("\n")
        index = stop

    def scan_quoted(start: int) -> int:
        quote = text[start]
        cursor = start + 1
        while cursor < length:
            char = text[cursor]
            if char == "\\":
                cursor += 2
                continue
            if char == quote:
                return cursor + 1
            if char == "\n":
                return cursor
            cursor += 1
        return length

    def scan_template(start: int) -> int:
        cursor = start + 1
        while cursor < length:
            char = text[cursor]
            if char == "\\":
                cursor += 2
                continue
            if char == "`":
                return cursor + 1
            if text.startswith("${", cursor):
                cursor = scan_substitution(cursor + 2)
                continue
            cursor += 1
        return length

    def scan_substitution(start: int) -> int:
        cursor = start
        depth = 0
        while cursor < length:
            char = text[cursor]
            if char in "'\"":
                cursor = scan_quoted(cursor)
                continue
            if char == "`":
                cursor = scan_template(cursor)
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                if depth == 0:
                    return cursor + 1
                depth -= 1
            cursor += 1
        return length

    def scan_regex(start: int) -> int:
        cursor = start + 1
        in_class = False
        while cursor < length:
            char = text[cursor]
            if char == "\\":
                cursor += 2
                continue
            if char == "\n":
                return cursor
            if char == "[":
                in_class = True
            elif char == "]":
                in_class = False
            elif char == "/" and not in_class:
                cursor += 1
                while cursor < length and text[cursor] in IDENT_CHARS:
                    cursor += 1
                return cursor
            cursor += 1
        return length

    while index < length:
        char = text[index]

        if char in " \t\r\n":
            line += text.count("\n", index, index + 1)
            index += 1
            continue

        if char == "/" and index + 1 < length and text[index + 1] == "/":
            stop = text.find("\n", index)
            emit("comment", index, length if stop == -1 else stop)
            continue

        if char == "/" and index + 1 < length and text[index + 1] == "*":
            stop = text.find("*/", index + 2)
            emit("comment", index, length if stop == -1 else stop + 2)
            continue

        if char == "/" and regex_can_start():
            emit("regex", index, scan_regex(index))
            continue

        if char in "'\"":
            emit("string", index, scan_quoted(index))
            continue

        if char == "`":
            emit("template", index, scan_template(index))
            continue

        if char in IDENT_CHARS:
            cursor = index
            while cursor < length and text[cursor] in IDENT_CHARS:
                cursor += 1
            emit("word", index, cursor)
            continue

        emit("punct", index, index + 1)

    return [token for token in tokens if token[0] != "comment"]


def console_arguments(tokens: list[tuple[str, str, int]], start: int) -> tuple[list[list[tuple[str, str, int]]], int]:
    groups: list[list[tuple[str, str, int]]] = []
    current: list[tuple[str, str, int]] = []
    depth = 0
    cursor = start
    while cursor < len(tokens):
        kind, body, _ = tokens[cursor]
        if kind == "punct":
            if body in OPENERS:
                depth += 1
            elif body in CLOSERS:
                if depth == 0:
                    if current:
                        groups.append(current)
                    return groups, cursor + 1
                depth -= 1
            elif body == "," and depth == 0:
                groups.append(current)
                current = []
                cursor += 1
                continue
        current.append(tokens[cursor])
        cursor += 1
    if current:
        groups.append(current)
    return groups, cursor


CONSOLE_BODY_ATTRIBUTES = frozenset({"body", "config", "data", "params", "request", "response"})

SUBSTITUTION = re.compile(r"\$\{([^{}]*)\}")


def interpolated_body(template: str) -> str | None:
    for span in SUBSTITUTION.findall(template):
        for attribute in re.findall(r"\.\s*([A-Za-z_$][\w$]*)", span):
            if attribute in CONSOLE_BODY_ATTRIBUTES:
                return f".{attribute}"
    return None


def script_findings(text: str) -> list[tuple[int, str, str]]:
    tokens = tokenize_script(text)
    findings: list[tuple[int, str, str]] = []
    index = 0
    while index + 3 < len(tokens):
        head = tokens[index]
        if head[:2] != ("word", "console"):
            index += 1
            continue
        if tokens[index + 1][:2] != ("punct", ".") or tokens[index + 2][0] != "word":
            index += 1
            continue
        method = tokens[index + 2][1]
        if method not in CONSOLE_METHODS or tokens[index + 3][:2] != ("punct", "("):
            index += 1
            continue

        groups, after = console_arguments(tokens, index + 4)
        for group in groups:
            if not group:
                continue
            line = group[0][2]
            call = f"console.{method}"
            if len(group) != 1 or group[0][0] not in ("string", "template"):
                findings.append((line, CONSOLE_ARGUMENT, f"{call}({render(''.join(part[1] for part in group))})"))
            elif "JSON.stringify" in group[0][1].replace(" ", ""):
                findings.append((line, CONSOLE_STRINGIFY, f"{call}({render(group[0][1])})"))
            elif group[0][0] == "template" and interpolated_body(group[0][1]):
                findings.append((line, CONSOLE_BODY, f"{call}({render(group[0][1])})"))
        index = after
    return findings


def dotted_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted_name(node.value)
        return f"{base}.{node.attr}" if base else None
    return None


def is_scanned_logger(name: str | None) -> bool:
    return bool(name) and name.rsplit(".", 1)[-1].lower() in LOG_OBJECTS


def is_logging_call(node: ast.Call) -> bool:
    if not isinstance(node.func, ast.Attribute) or node.func.attr not in LOG_METHODS:
        return False
    return is_scanned_logger(dotted_name(node.func.value))


def private_reference(node: ast.expr) -> str | None:
    if isinstance(node, ast.Attribute) and node.attr in PRIVATE_NAMES:
        return f".{node.attr}"
    if isinstance(node, ast.Name) and node.id in PRIVATE_NAMES:
        return node.id
    if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) and node.slice.value in PRIVATE_NAMES:
        return f"[{node.slice.value!r}]"
    return None


def body_reference(node: ast.expr, depth: int = 0) -> str | None:
    if depth > 6:
        return None
    if isinstance(node, ast.Name) and node.id in BODY_NAMES:
        return node.id
    if isinstance(node, ast.Attribute):
        if node.attr in BODY_ATTRIBUTES or (node.attr in SUB_BODY_KEYS and body_reference(node.value, depth + 1)):
            return f".{node.attr}"
        return None
    if isinstance(node, ast.Subscript):
        key = node.slice.value if isinstance(node.slice, ast.Constant) else None
        if key in DOCUMENT_KEYS:
            return f"[{key!r}]"
        receiver = body_reference(node.value, depth + 1)
        return f"{receiver}[...]" if receiver and key is None else None
    if not isinstance(node, ast.Call):
        return None
    if isinstance(node.func, ast.Attribute):
        if node.func.attr == "json" and not node.args:
            return ".json()"
        if node.func.attr == "get" and node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and first.value in DOCUMENT_KEYS:
                return f".get({first.value!r})"
        if node.func.attr in STRINGIFIERS and node.args:
            return body_reference(node.args[0], depth + 1)
    if isinstance(node.func, ast.Name) and node.func.id in STRINGIFIERS and node.args:
        return body_reference(node.args[0], depth + 1)
    return None


def structural_values(expression: ast.expr) -> list[ast.expr]:
    values = [expression]
    for inner in ast.walk(expression):
        if isinstance(inner, ast.FormattedValue):
            values.append(inner.value)
        elif isinstance(inner, ast.BinOp) and isinstance(inner.op, ast.Mod):
            right = inner.right
            values.extend(right.elts if isinstance(right, ast.Tuple) else [right])
        elif isinstance(inner, (ast.List, ast.Set, ast.Tuple)):
            values.extend(inner.elts)
        elif isinstance(inner, ast.Dict):
            values.extend(value for value in inner.values if value is not None)
    return values


def logged_values(node: ast.Call, bindings: dict[str, ast.expr] | None = None) -> list[ast.expr]:
    bindings = bindings or {}
    direct: list[ast.expr] = []
    for argument in list(node.args) + [keyword.value for keyword in node.keywords]:
        direct.extend(structural_values(argument))

    values = list(direct)
    for value in direct:
        if isinstance(value, ast.Name) and value.id in bindings:
            values.extend(structural_values(bindings[value.id]))
    return values


def body_of(scope: ast.AST):
    nested = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
    pending = list(ast.iter_child_nodes(scope))
    while pending:
        node = pending.pop()
        yield node
        if not isinstance(node, nested):
            pending.extend(ast.iter_child_nodes(node))


def single_bindings(scope: ast.AST) -> dict[str, ast.expr]:
    assigned: dict[str, list[ast.expr]] = {}

    for node in body_of(scope):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assigned.setdefault(target.id, []).append(node.value)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            assigned.setdefault(node.target.id, []).append(node.value)
        elif isinstance(node, (ast.For, ast.AsyncFor)) and isinstance(node.target, ast.Name):
            assigned.setdefault(node.target.id, []).append(node.iter)
        elif isinstance(node, ast.withitem) and isinstance(node.optional_vars, ast.Name):
            assigned.setdefault(node.optional_vars.id, []).append(node.context_expr)

    return {name: values[0] for name, values in assigned.items() if len(values) == 1}


def scopes_of(tree: ast.AST):
    yield tree
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            yield node


def logger_bindings(target: ast.expr, value: ast.expr):
    if (
        isinstance(target, (ast.Tuple, ast.List))
        and isinstance(value, (ast.Tuple, ast.List))
        and len(target.elts) == len(value.elts)
        and not any(isinstance(element, ast.Starred) for element in (*target.elts, *value.elts))
    ):
        for member, expression in zip(target.elts, value.elts):
            yield from logger_bindings(member, expression)
        return

    for call in ast.walk(value):
        if isinstance(call, ast.Call) and dotted_name(call.func) == "logging.getLogger":
            yield target, call is value


def alias_findings(tree: ast.AST, source: str) -> list[tuple[int, str, str]]:
    findings: list[tuple[int, str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)):
            targets = [node.target]
        else:
            continue
        if node.value is None:
            continue
        for target in targets:
            for binding, direct in logger_bindings(target, node.value):
                name = dotted_name(binding)
                if direct and name and is_scanned_logger(name):
                    continue
                label = name or ast.get_source_segment(source, binding) or ast.unparse(binding)
                description = f"{label} = logging.getLogger(...)"
                if not direct:
                    description = f"{label} receives logging.getLogger(...) through an uninspectable value"
                findings.append((binding.lineno, LOG_ALIAS, description))
    return findings


def python_findings(text: str) -> list[tuple[int, str, str]]:
    try:
        tree = ast.parse(text)
    except SyntaxError as error:
        return [(0, LOG_PRIVATE, f"could not parse: {error}")]

    findings: list[tuple[int, str, str]] = alias_findings(tree, text)

    for scope in scopes_of(tree):
        bindings = single_bindings(scope)
        for node in body_of(scope):
            if not isinstance(node, ast.Call) or not is_logging_call(node):
                continue
            call = dotted_name(node.func) or "logger"
            for value in logged_values(node, bindings):
                for inner in ast.walk(value):
                    if not isinstance(inner, ast.expr):
                        continue
                    reference = private_reference(inner)
                    if reference:
                        line = getattr(inner, "lineno", node.lineno)
                        findings.append((line, LOG_PRIVATE, f"{call}(... {reference} ...)"))
                reference = body_reference(value)
                if reference:
                    line = getattr(value, "lineno", node.lineno)
                    findings.append((line, LOG_BODY, f"{call}(... {reference} ...)"))

    return sorted(set(findings))


def files_in(tree: str, extensions: tuple[str, ...]):
    base = ROOT / tree
    if not base.is_dir():
        return
    for path in sorted(base.rglob("*")):
        if path.suffix not in extensions or not path.is_file():
            continue
        parts = path.relative_to(base).parts
        if any(part in SKIP_ANYWHERE for part in parts):
            continue
        if parts[:1] and parts[0] in SKIP_AT_TOP:
            continue
        yield path


def scan() -> tuple[list[str], int]:
    violations: list[str] = []
    checked = 0

    for tree in CLIENT_TREES:
        for path in files_in(tree, TS):
            checked += 1
            relative = path.relative_to(ROOT)
            for line, rule, detail in script_findings(path.read_text(encoding="utf-8-sig", errors="replace")):
                violations.append(f"{relative}:{line}: {rule}: {detail}")

    for path in files_in(BACKEND_TREE, (".py",)):
        checked += 1
        relative = path.relative_to(ROOT)
        for line, rule, detail in python_findings(path.read_text(encoding="utf-8-sig", errors="replace")):
            violations.append(f"{relative}:{line}: {rule}: {detail}")

    return violations, checked


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail when a log line can carry a credential or an email address.")
    parser.add_argument("--list-rules", action="store_true", help="print the rules this gate enforces and exit")
    arguments = parser.parse_args()

    if arguments.list_rules:
        for rule, explanation in sorted(RULES.items()):
            print(f"{rule}: {explanation}")
        return 0

    violations, checked = scan()

    if violations:
        print(f"Logging that can carry a credential or an email address ({len(violations)} found):\n", file=sys.stderr)
        for entry in violations:
            print(f"  {entry}", file=sys.stderr)
        print("", file=sys.stderr)
        for rule in sorted({entry.split(": ")[1] for entry in violations}):
            print(f"  {rule}: {RULES[rule]}", file=sys.stderr)
        print(
            "\nThe rule and its scope are in docs/GATES.md,"
            '\n"The logging privacy gate".',
            file=sys.stderr,
        )
        return 1

    print(f"No credential-carrying log line in {checked} source files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
