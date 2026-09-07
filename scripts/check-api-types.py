#!/usr/bin/env python3
"""Fail when a shared TypeScript type requires a field the API never sends.

The rule and its scope are stated in docs/ARCHITECTURE.md under "The API type
drift gate". This script is the mechanical half of that rule; keep the two in
step.

One direction only. A field an endpoint sends that no type models is dead
weight: TypeScript never surfaces it, so nothing reads it and nothing breaks.
A field a type declares *required* that the endpoint never sends is different
in kind -- every read of it type-checks and every read of it is undefined at
run time, and no amount of care at the call site can catch that, because the
type is the thing being trusted.

Matching goes through paths, never through names. drf-spectacular names its
components after serializer classes, so a component and an interface can share
a word and describe unrelated endpoints: this repository has documents.Document
and companies.CompanyDocument side by side, both with upload endpoints and both
producing a component whose name contains "Document". Comparing those by name
reports drift that does not exist and misses drift that does. So the gate reads
the URL each service function actually calls, finds the operation the schema
declares at that path and verb, and compares the TypeScript generic against
*that operation's 2xx response schema*.

Field names are compared with separators removed and case folded, because the
wire is camelCase (djangorestframework-camel-case renders it) while a schema
component may carry either form depending on the camelize hook. "address_line_1"
and "addressLine1" are the same field and must not read as two.

LEGACY carries the findings that predate the gate, keyed by
"<TS type>:<component>" and valued by a count. The count may only shrink: a
number higher than what is there fails as loudly as a number lower, so the list
cannot quietly outlive the problem it records.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SHARED = ROOT / "packages/shared/src"

LEGACY: dict[str, int] = {
    "DeviceToken:DeviceToken": 1,
    "FeatureFlag:FeatureFlag": 2,
    "FinancialProfile:FinancialProfile": 2,
    "UserPreferences:UserPreferences": 2,
}

ENDPOINT_BLOCK = re.compile(r"export const (\w+)\s*=\s*\{(.*?)^\}", re.S | re.M)
ENDPOINT_ENTRY = re.compile(r"^\s*(\w+):\s*(?:\([^)]*\)\s*=>\s*)?[`']([^`'\n]+)[`']", re.M)
CALL = re.compile(
    r"apiClient\.(get|post|put|patch|delete)(?:<([^>]*(?:<[^>]*>)?[^>]*)>)?\s*\(\s*([A-Z_]+\.\w+)",
    re.S,
)
INTERFACE = re.compile(r"^export interface (\w+)([^{]*)\{(.*?)^\}", re.S | re.M)
FIELD = re.compile(r"^\s*(\w+)(\??):\s*([^;]+);", re.M)
PICK = re.compile(r"Pick<\s*(\w+)\s*,\s*([^>]+)>")
EXTENDS = re.compile(r"^\s*extends\s+([\w,\s]+)$")
GENERIC_NOISE = {"PaginatedResponse", "Array", "Promise", "File", "Record", "Partial", "Blob"}


def field_key(name: str) -> str:
    return name.replace("_", "").lower()


def url_shape(template: str) -> str:
    without_parameters = re.sub(r"\$\{[^}]+\}", "*", template)
    without_parameters = re.sub(r"\{[^}]+\}", "*", without_parameters)
    return without_parameters.rstrip("/") + "/"


def declared_endpoints() -> dict[str, str]:
    text = (SHARED / "constants/api.ts").read_text()
    out: dict[str, str] = {}
    for block in ENDPOINT_BLOCK.finditer(text):
        constant, body = block.group(1), block.group(2)
        for entry in ENDPOINT_ENTRY.finditer(body):
            key, template = entry.group(1), entry.group(2).strip()
            if template.startswith("/"):
                out[f"{constant}.{key}"] = url_shape(template)
    return out


def service_calls() -> dict[tuple[str, str], set[str]]:
    endpoints = declared_endpoints()
    calls: dict[tuple[str, str], set[str]] = {}
    for path in sorted((SHARED / "services").glob("*.ts")):
        for verb, generic, constant in CALL.findall(path.read_text()):
            url = endpoints.get(constant)
            if not url:
                continue
            named = set(re.findall(r"\b([A-Z]\w+)", generic or "")) - GENERIC_NOISE
            if named:
                calls.setdefault((verb, url), set()).update(named)
    return calls


def interfaces() -> dict[str, dict[str, bool]]:
    declared: dict[str, tuple[dict[str, bool], list[str]]] = {}
    for path in sorted((SHARED / "types").rglob("*.ts")):
        for name, heritage, body in INTERFACE.findall(path.read_text()):
            fields = {field_key(f): optional == "?" for f, optional, _type in FIELD.findall(body)}
            for _base, picked in PICK.findall(heritage):
                fields.update({field_key(v): False for v in re.findall(r"'([^']+)'", picked)})
            bases: list[str] = []
            plain = EXTENDS.match(heritage.strip().replace("{", ""))
            if plain and "Pick<" not in heritage:
                bases = [b.strip() for b in plain.group(1).split(",") if b.strip()]
            declared[name] = (fields, bases)

    resolved: dict[str, dict[str, bool]] = {}

    def resolve(name: str, seen: tuple[str, ...] = ()) -> dict[str, bool]:
        if name in resolved:
            return resolved[name]
        if name not in declared or name in seen:
            return {}
        own, bases = declared[name]
        merged: dict[str, bool] = {}
        for base in bases:
            merged.update(resolve(base, seen + (name,)))
        merged.update(own)
        resolved[name] = merged
        return merged

    return {name: resolve(name) for name in declared}


def schema_parts(document: dict) -> tuple[dict[str, dict[str, bool]], dict[tuple[str, str], set[str]]]:
    components: dict[str, dict[str, bool]] = {}
    for name, body in (document.get("components", {}).get("schemas") or {}).items():
        properties = body.get("properties") or {}
        if properties:
            components[name] = {
                field_key(k): bool(v.get("writeOnly", False)) for k, v in properties.items()
            }

    responses: dict[tuple[str, str], set[str]] = {}
    for raw_path, operations in (document.get("paths") or {}).items():
        shape = url_shape(raw_path)
        for verb, operation in (operations or {}).items():
            if verb not in {"get", "post", "put", "patch", "delete"}:
                continue
            referenced: set[str] = set()
            for code, response in (operation.get("responses") or {}).items():
                if str(code).startswith("2"):
                    referenced.update(
                        re.findall(r"#/components/schemas/(\w+)", json.dumps(response))
                    )
            if referenced:
                responses.setdefault((verb, shape), set()).update(referenced)
    return components, responses


def scan(schema_path: Path):
    document = yaml.safe_load(schema_path.read_text())
    components, responses = schema_parts(document)
    calls = service_calls()
    declared = interfaces()

    findings: list[tuple[str, str, str, list[str]]] = []
    matched = 0

    for (verb, url), names in sorted(calls.items()):
        referenced = responses.get((verb, url))
        if not referenced:
            continue
        matched += 1
        for name in sorted(names):
            fields = declared.get(name)
            if not fields:
                continue
            best, overlap = None, 0
            for component in sorted(referenced):
                shape = components.get(component)
                if not shape:
                    continue
                shared_fields = len(set(fields) & set(shape))
                if shared_fields > overlap:
                    best, overlap = component, shared_fields
            if not best:
                continue
            absent = sorted(
                field
                for field, optional in fields.items()
                if not optional and field not in components[best]
            )
            if absent:
                findings.append((f"{verb.upper()} {url}", name, best, absent))
    return findings, matched


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", required=True, type=Path)
    parser.add_argument("--explain", action="store_true")
    arguments = parser.parse_args()

    if arguments.explain:
        print(__doc__)
        return 0

    findings, matched = scan(arguments.schema)

    counts: dict[str, int] = {}
    for _endpoint, name, component, absent in findings:
        counts[f"{name}:{component}"] = counts.get(f"{name}:{component}", 0) + len(absent)

    new = {key: count for key, count in counts.items() if count > LEGACY.get(key, 0)}
    stale = sorted(key for key, pinned in LEGACY.items() if counts.get(key, 0) < pinned)

    if new:
        print(
            f"These shared types require a field their endpoint never sends ({len(new)}):\n",
            file=sys.stderr,
        )
        for endpoint, name, component, absent in findings:
            if f"{name}:{component}" in new:
                print(f"  {endpoint}", file=sys.stderr)
                print(f"    {name} declares {', '.join(absent)} as required", file=sys.stderr)
                print(f"    {component} does not carry them\n", file=sys.stderr)
        print(
            "Every read of such a field type-checks and is undefined at run time.\n"
            "Mark it optional, remove it, or make the serializer send it.\n"
            'The rule is in docs/ARCHITECTURE.md, "The API type drift gate".',
            file=sys.stderr,
        )
        return 1

    if stale:
        print(f"These pinned counts are higher than what is there ({len(stale)}):\n", file=sys.stderr)
        for key in stale:
            print(f"  {key}: pinned {LEGACY[key]}, found {counts.get(key, 0)}", file=sys.stderr)
        print("\nLower the count in LEGACY in this script; it may only shrink.", file=sys.stderr)
        return 1

    print(
        f"No shared type requires an absent field across {matched} matched endpoints "
        f"({sum(LEGACY.values())} known findings still in LEGACY)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
