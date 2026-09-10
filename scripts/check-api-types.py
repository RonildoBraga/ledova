#!/usr/bin/env python3
"""Fail when shared response fields or trading event names drift from the API.

The rule and its scope are stated in docs/GATES.md under "The API type
drift gate". This script is the mechanical half of that rule; keep the two in
step.

Response fields are checked in one direction. A field an endpoint sends that no type models is dead
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

Trading event names are compared in both directions against the generated stream
metadata. The separately declared connection event needs no invalidation listener.

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

TYPE_DEBT: dict[str, tuple[int, str]] = {}

SCHEMA_DEBT: dict[str, tuple[int, str]] = {
    "IssuerSubscription:OfferingDetail": (
        11,
        "offerings/views/offering.py subscriptions returns "
        "self.get_paginated_response(IssuerSubscriptionSerializer(page, many=True).data), which "
        "check-schema-responses.py does not see: it looks for Response(...) and this is a third "
        "spelling. The generator falls back to OfferingDetailSerializer. The interface is correct; "
        "tracked as a follow-up to #211.",
    ),
    "CancelOrderMessageResponse:TransferOrderList": (7, "tokens/views/trading_order.py builds this body itself while get_serializer_class names a TransferOrder serializer, so the generator documents the wrong shape. The interface is correct. In check-schema-responses.py's LEGACY; tracked by #211."),
    "ApprovalStatusResponse:TransferOrderList": (7, "tokens/views/trading_order.py builds this body itself while get_serializer_class names a TransferOrder serializer, so the generator documents the wrong shape. The interface is correct. In check-schema-responses.py's LEGACY; tracked by #211."),
    "ApprovalDataResponse:TransferOrderList": (1, "tokens/views/trading_order.py builds this body itself while get_serializer_class names a TransferOrder serializer, so the generator documents the wrong shape. The interface is correct. In check-schema-responses.py's LEGACY; tracked by #211."),
    "MarketData:ShareTokenList": (
        7,
        "tokens/views/trading_token.py market_data returns Response(market_data), a body built "
        "into a local, so the generator falls back to the viewset's serializer. The interface is "
        "correct. check-schema-responses.py does not see this spelling either - it looks for a "
        "dict literal, and this is a name. Tracked as a follow-up to #211.",
    ),
    "OrderBook:ShareTokenList": (
        3,
        "tokens/views/trading_token.py order_book returns Response(order_book), the same shape as "
        "market_data above and invisible to check-schema-responses.py for the same reason. The "
        "interface is correct. Tracked as a follow-up to #211.",
    ),
    "OrderModificationMessageResponse:TransferOrderList": (
        9,
        "tokens/views/trading_order.py create_message builds its own body while "
        "get_serializer_class names TransferOrderCreateSerializer, and the generator documents "
        "neither. The interface is correct. Tracked as a follow-up to #211.",
    ),
    "AccountExportData:UserProfile": (
        9,
        "users/views/user_profile.py export-data returns lifecycle.export_account_data(user), a "
        "literal body, so the generator falls back to the viewset's serializer. The interface is "
        "correct. In check-schema-responses.py's LEGACY; tracked by #211.",
    ),
    "TokenIssuancesResponse:ShareTokenDetail": (
        5,
        "tokens/views/share_token.py issuances returns a literal paginated body and the generator "
        "falls back to the viewset's serializer. The interface is correct. Tracked by #211.",
    ),
    "CompanyStats:CompanyDetail": (
        3,
        "companies/views/company.py stats returns company_stats(...), a literal body, so the "
        "generator falls back to the viewset's serializer. The interface is correct. Tracked by "
        "#211.",
    ),
    "CapitalIncreaseResponse:CapitalIncreaseList": (
        2,
        "tokens/views/capital_increase.py list returns a literal body carrying count and results, "
        "and the generator documents the row serializer. The interface is correct. Tracked by "
        "#211.",
    ),
    "MarkAllReadResponse:Notification": (
        1,
        "users/views/notification.py mark_all_read returns {'marked': n}, a literal body, so the "
        "generator falls back to the viewset's serializer. The interface is correct. Tracked by "
        "#211.",
    ),
    "UnreadCountResponse:Notification": (
        1,
        "users/views/notification.py unread_count returns {'unreadCount': n}, a literal body, so "
        "the generator falls back to the viewset's serializer. The interface is correct. Tracked "
        "by #211.",
    ),
}

ENDPOINT_OPENS = re.compile(r"export const (\w+)\s*=\s*\{")
ENDPOINT_ENTRY = re.compile(r"^\s*(\w+):\s*(?:\([^)]*\)\s*=>\s*)?[`']([^`'\n]+)[`']", re.M)
# Any receiver, not only one spelled "apiClient": the shape is already specific
# enough without it -- a verb, a type argument, and an endpoint constant - and
# pinning the receiver's name means renaming a parameter silently stops the gate
# checking those calls.
CALL = re.compile(
    r"\b\w+\.(get|post|put|patch|delete)(?:<([^>]*(?:<[^>]*>)?[^>]*)>)?\s*\(\s*([A-Z][A-Z0-9_]*(?:\.\w+)+)(?=\s*[(,)])",
    re.S,
)
HTTP_CALL = re.compile(r"\b\w+\.(?:get|post|put|patch|delete)\s*(?=<|\()")
NONCODE = re.compile(
    r"//[^\n]*|/\*.*?\*/|\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`",
    re.S,
)
INTERFACE = re.compile(r"^export interface (\w+)([^{]*)\{", re.M)
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


def _balanced_body(text: str, brace: int) -> str:
    """The text between a `{` and its matching `}`.

    A regex ending at the first line-starting `}` merges a single-line group into
    the next one: USER_PREFERENCES_ENDPOINTS = { BASE: ... } as const; closes
    mid-line, so IDENTITY_VERIFICATION_ENDPOINTS was swallowed whole and its two
    endpoints went unresolvable.
    """
    depth = 0
    masked = mask_noncode(text)
    for index in range(brace, len(text)):
        if masked[index] == "{":
            depth += 1
        elif masked[index] == "}":
            depth -= 1
            if depth == 0:
                return text[brace + 1 : index]
    return ""


def declared_endpoints() -> dict[str, str]:
    """Every endpoint group under constants/, nested groups included.

    OFFERING, TRADING, SUBSCRIPTION and DIRECTORY live in constants/business/.
    Reading api.ts alone left every service call through them unmatched, which
    is most of the product - and it is why this gate did not catch #248, an
    instance of exactly the drift it exists to find.

    Groups nest: TRADING_ENDPOINTS.WHITELIST.STATUS is a function two levels
    down, so the key is the dotted path a caller actually writes.
    """
    out: dict[str, str] = {}

    for path in sorted((SHARED / "constants").rglob("*.ts")):
        text = path.read_text()
        for opening in ENDPOINT_OPENS.finditer(text):
            trail = [opening.group(1)]
            body = re.sub(r"=>\s*\n\s*", "=> ", _balanced_body(text, opening.end() - 1))
            for line in body.splitlines():
                stripped = line.strip()
                entry = ENDPOINT_ENTRY.match(line)
                if entry and entry.group(2).strip().startswith("/"):
                    out[".".join(trail + [entry.group(1)])] = url_shape(entry.group(2).strip())
                    continue
                opening = re.match(r"(\w+)\s*:\s*\{\s*$", stripped)
                if opening:
                    trail.append(opening.group(1))
                elif stripped.startswith("}") and len(trail) > 1:
                    trail.pop()
    return out


class Unresolvable(Exception):
    """A service call whose endpoint or response shape cannot be inspected."""


def mask_noncode(text: str) -> str:
    return NONCODE.sub(lambda match: re.sub(r"[^\n]", " ", match.group()), text)


def top_level_fields(body: str) -> dict[str, bool]:
    flattened = list(body)
    depth = 0
    for index, char in enumerate(mask_noncode(body)):
        if char == "{":
            depth += 1
        if depth and char != "\n":
            flattened[index] = " "
        if char == "}":
            depth -= 1
    return {
        field_key(name): optional == "?"
        for name, optional, _type in FIELD.findall("".join(flattened))
    }


def ends_url_argument(masked: str, end: int) -> bool:
    while end < len(masked) and masked[end].isspace():
        end += 1
    if end < len(masked) and masked[end] == "(":
        depth = 1
        end += 1
        while end < len(masked) and depth:
            if masked[end] == "(":
                depth += 1
            elif masked[end] == ")":
                depth -= 1
            end += 1
    return masked[end:].lstrip().startswith((",", ")"))


def service_calls() -> dict[tuple[str, str], set[str]]:
    endpoints = declared_endpoints()
    calls: dict[tuple[str, str], set[str]] = {}
    unresolved: list[str] = []
    for path in sorted((SHARED / "services").glob("*.ts")):
        source = path.read_text()
        masked = mask_noncode(source)
        for site in HTTP_CALL.finditer(masked):
            matched = CALL.match(source, site.start())
            if matched is None or not ends_url_argument(masked, matched.end()):
                line = source.count("\n", 0, site.start()) + 1
                unresolved.append(f"{path.name}:{line}: use a resolvable endpoint constant directly")
                continue
            verb, generic, constant = matched.groups()
            url = endpoints.get(constant)
            if not url:
                # Skipping here is how 53 of 114 call sites went unchecked while the
                # success line reported a match count nobody diffs. A constant this
                # gate cannot resolve is a hole in its coverage, not a call to ignore.
                unresolved.append(f"{path.name}: {constant}")
                continue
            named = set(re.findall(r"\b([A-Z]\w*)", generic or "")) - GENERIC_NOISE
            if named:
                calls.setdefault((verb, url), set()).update(named)

    if unresolved:
        raise Unresolvable(
            "These service calls do not resolve to endpoint constants, so the "
            "endpoints they reach cannot be checked:\n  " + "\n  ".join(sorted(set(unresolved)))
        )
    return calls


def interfaces() -> dict[str, dict[str, bool]]:
    declared: dict[str, tuple[dict[str, bool], list[str]]] = {}
    for path in sorted((SHARED / "types").rglob("*.ts")):
        source = path.read_text()
        for opening in INTERFACE.finditer(source):
            name, heritage = opening.groups()
            fields = top_level_fields(_balanced_body(source, opening.end() - 1))
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


def response_components(name: str, raw: dict, seen: tuple[str, ...] = ()) -> set[str]:
    name = _unwrapped(name, raw)
    if name in seen:
        return set()
    body = raw.get(name) or {}
    choices = body.get("oneOf") or body.get("anyOf") or []
    references = [choice["$ref"].rsplit("/", 1)[-1] for choice in choices if "$ref" in choice]
    if references:
        return set().union(*(response_components(ref, raw, seen + (name,)) for ref in references))
    return {name}


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
                    component for name in referenced for component in response_components(name, raw)
                )
    return components, responses


def scan(schema_path: Path):
    document = yaml.safe_load(schema_path.read_text())
    components, responses = schema_parts(document)
    calls = service_calls()
    declared = interfaces()
    unknown = sorted(
        f"{verb.upper()} {url}: {name}"
        for (verb, url), names in calls.items()
        for name in names
        if not declared.get(name)
    )
    if unknown:
        raise Unresolvable(
            "These response types have no inspectable shared interface. Use a concrete response "
            "type or extend the gate's parser:\n  " + "\n  ".join(unknown)
        )

    findings: list[tuple[str, str, str, list[str]]] = []
    matched = 0
    unmatched: list[str] = []

    for (verb, url), names in sorted(calls.items()):
        referenced = responses.get((verb, url))
        if not referenced:
            # A call the schema has no operation for. Not a failure - the endpoint
            # may be one of #211's schemaless views - but counting only the matches
            # makes a partial number read as a total.
            unmatched.append(f"{verb.upper()} {url}")
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
    return findings, matched, sorted(set(unmatched))


def trading_event_drift(document: dict) -> list[str]:
    path = declared_endpoints().get("TRADING_ENDPOINTS.EVENTS.STREAM")
    if not path:
        raise Unresolvable("The trading stream endpoint constant is not resolvable.")
    try:
        stream = document["paths"][path]["get"]["responses"]["200"]["content"]["text/event-stream"]["schema"]
        events = stream["x-sse-events"]
        connection_event = stream["x-sse-connection-event"]
    except (KeyError, TypeError) as error:
        raise Unresolvable("The trading stream schema must declare its events and connection event.") from error
    if (
        not isinstance(events, list)
        or not events
        or any(not isinstance(event, str) or not event for event in events)
        or len(set(events)) != len(events)
        or not isinstance(connection_event, str)
        or connection_event not in events
    ):
        raise Unresolvable("The trading stream events must be unique strings including the connection event.")

    declarations = []
    for source in sorted((SHARED / "constants").rglob("*.ts")):
        text = NONCODE.sub(
            lambda match: " " if match.group().startswith(("//", "/*")) else match.group(), source.read_text()
        )
        masked = mask_noncode(text)
        for match in re.finditer(r"\bexport\s+type\s+TradingEventType\s*=([^;]*);", masked):
            declarations.append(text[match.start(1) : match.end(1)].strip())
    if len(declarations) != 1:
        raise Unresolvable("Declare exactly one shared TradingEventType string-literal union.")
    body = declarations[0]
    literal = r'''(?:'[^'\\\n]+'|"[^"\\\n]+")'''
    if not re.fullmatch(rf"\|?\s*{literal}(?:\s*\|\s*{literal})*\s*", body):
        raise Unresolvable("TradingEventType must be an inspectable string-literal union.")
    client = {match[1:-1] for match in re.findall(literal, body)}
    server = set(events) - {connection_event}
    errors = []
    if server - client:
        errors.append("No client invalidation for server events: " + ", ".join(sorted(server - client)))
    if client - server:
        errors.append("Client listens for events the server never sends: " + ", ".join(sorted(client - server)))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", required=True, type=Path)
    parser.add_argument("--explain", action="store_true")
    arguments = parser.parse_args()

    if arguments.explain:
        print(__doc__)
        return 0

    try:
        findings, matched, unmatched = scan(arguments.schema)
        event_errors = trading_event_drift(yaml.safe_load(arguments.schema.read_text()))
    except Unresolvable as error:
        print(f"{error}\n", file=sys.stderr)
        print(
            "Use resolvable endpoint constants and concrete shared response types, or extend the gate's parser.",
            file=sys.stderr,
        )
        return 1

    if event_errors:
        print("Trading event names differ between the server and client:\n", file=sys.stderr)
        for error in event_errors:
            print(f"  {error}", file=sys.stderr)
        return 1

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
            'The rule is in docs/GATES.md, "The API type drift gate".',
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
        f"No shared type requires an absent field across {matched} of "
        f"{matched + len(unmatched)} endpoints reached by a resolvable call "
        f"({sum(pinned_counts[k] for k in TYPE_DEBT)} known type findings, "
        f"{sum(pinned_counts[k] for k in SCHEMA_DEBT)} awaiting the schema fixes in #211; "
        f"{len(unmatched)} reaching no operation the schema declares)."
    )
    print("TradingEventType matches every invalidating event in the stream schema in both directions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
