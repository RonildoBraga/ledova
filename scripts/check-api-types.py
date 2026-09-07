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

Two lists carry what predates the gate, both keyed by "<TS type>:<component>"
and both valued by a count with a reason. The counts may only shrink: a number
higher than what is there fails as loudly as a number lower, so neither list can
quietly outlive the problem it records.

They are separate because they are different problems and the distinction is
load-bearing. TYPE_DEBT is a type that promises what the API does not send --
the thing this gate exists to catch. SCHEMA_DEBT is the reverse: the TypeScript
is correct and the *schema* is wrong, because a view builds its own Response
with a serializer other than the one get_serializer_class names, and the
generator documents the latter. Recording those as type debt would assert
something false about correct code, and an allowlist that asserts something
false is worse than no allowlist, because the next reader trusts it. #211
empties SCHEMA_DEBT; when it does, the counts here fail as too high, which is
the intended way to find out.
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

TYPE_DEBT: dict[str, tuple[int, str]] = {
    "FinancialProfile:FinancialProfile": (
        4,
        "FinancialProfileSerializer carries exclude = ('created_at', 'updated_at') while the "
        "interface extends BaseEntity, which declares createdAt and updatedAt required. Two "
        "fields on each of POST and PATCH. Fix by narrowing the interface, not by widening the "
        "serializer: nothing reads them.",
    ),
    "DeviceToken:DeviceToken": (
        1,
        "DeviceTokenSerializer lists created_at but not updated_at, while the interface extends "
        "BaseEntity, which declares both required.",
    ),
    "UserPreferences:UserPreferences": (
        2,
        "UserPreferencesSerializer carries exclude = ('created_at', 'updated_at') while the "
        "interface extends BaseEntity, which declares both required.",
    ),
    "Company:CompanyUpdate": (
        27,
        "CompanyViewSet declares no update or partial_update, so DRF answers PATCH with "
        "CompanyUpdateSerializer - fifteen write fields - while the service is typed "
        "apiClient.patch<Company>. All three call sites invalidate rather than read the "
        "response, so nothing is broken today.",
    ),
}

SCHEMA_DEBT: dict[str, tuple[int, str]] = {
    "AccountExportData:UserProfile": (
        33,
        "users/views/user_profile.py:39 returns lifecycle.export_account_data(request.user), a "
        "plain dict, so the generator falls back to the viewset's serializer. The interface is "
        "correct. Tracked by #211.",
    ),
    "TokenHoldersResponse:ShareTokenDetail": (
        3,
        "tokens/views/share_token.py:125 builds its own response and the generator falls back to "
        "the viewset's serializer. The interface is correct. Tracked by #211.",
    ),
    "CompanyShareToken:ShareTokenCreate": (
        8,
        "tokens/views/share_token.py:71 returns Response(ShareTokenDetailSerializer(token).data) "
        "while get_serializer_class names ShareTokenCreateSerializer for the create action. The "
        "interface is correct. Tracked by #211.",
    ),
    "CapitalIncreaseRequest:CapitalIncreaseCreate": (
        11,
        "tokens/views/capital_increase.py:56 returns Response(CapitalIncreaseDetailSerializer("
        "capital_increase).data) while get_serializer_class names the create serializer. The "
        "interface is correct. Tracked by #211.",
    ),
}

ENDPOINT_BLOCK = re.compile(r"export const (\w+)\s*=\s*\{(.*?)^\}", re.S | re.M)
ENDPOINT_ENTRY = re.compile(r"^\s*(\w+):\s*(?:\([^)]*\)\s*=>\s*)?[`']([^`'\n]+)[`']", re.M)
# Any receiver, not only one spelled "apiClient": the shape is already specific
# enough without it -- a verb, a type argument, and an endpoint constant - and
# pinning the receiver's name means renaming a parameter silently stops the gate
# checking those calls.
CALL = re.compile(
    r"\b\w+\.(get|post|put|patch|delete)(?:<([^>]*(?:<[^>]*>)?[^>]*)>)?\s*\(\s*([A-Z_]+\.\w+)",
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


def _unwrapped(name: str, raw: dict) -> str:
    """A paginated wrapper describes the page, not the row the type models.

    `PaginatedAssetList` carries count/next/previous/results, so comparing an
    `Asset` interface against it reports every field of Asset as absent. The
    shape the caller's type argument describes is the one inside `results`.
    """
    body = raw.get(name) or {}
    results = (body.get("properties") or {}).get("results") or {}
    reference = (results.get("items") or {}).get("$ref", "")
    inner = reference.rsplit("/", 1)[-1]
    return inner if inner in raw else name


def schema_parts(document: dict) -> tuple[dict[str, dict[str, bool]], dict[tuple[str, str], set[str]]]:
    raw = document.get("components", {}).get("schemas") or {}
    components: dict[str, dict[str, bool]] = {}
    for name, body in raw.items():
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
                responses.setdefault((verb, shape), set()).update(
                    _unwrapped(name, raw) for name in referenced
                )
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
            candidates = [c for c in sorted(referenced) if c in components]
            if not candidates:
                continue
            if len(candidates) == 1:
                # One candidate is no choice at all, so compare it however little
                # it overlaps. Requiring overlap here would silently skip a type
                # that is entirely wrong, which is the case most worth reporting.
                best = candidates[0]
            else:
                best, overlap = None, 0
                for component in candidates:
                    shared_fields = len(set(fields) & set(components[component]))
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

    pinned_counts = {key: entry[0] for key, entry in {**TYPE_DEBT, **SCHEMA_DEBT}.items()}
    new = {key: count for key, count in counts.items() if count > pinned_counts.get(key, 0)}
    stale = sorted(key for key, pinned in pinned_counts.items() if counts.get(key, 0) < pinned)

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
            print(f"  {key}: pinned {pinned_counts[key]}, found {counts.get(key, 0)}", file=sys.stderr)
        print(
            "\nLower the count in TYPE_DEBT or SCHEMA_DEBT in this script; they may only shrink.",
            file=sys.stderr,
        )
        return 1

    print(
        f"No shared type requires an absent field across {matched} matched endpoints "
        f"({sum(pinned_counts[k] for k in TYPE_DEBT)} known type findings, "
        f"{sum(pinned_counts[k] for k in SCHEMA_DEBT)} awaiting the schema fixes in #211)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
