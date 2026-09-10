#!/usr/bin/env python3

import argparse
import difflib
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "backend/schema/openapi.json"


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def canonical_document(path):
    document = json.loads(path.read_text(), object_pairs_hook=unique_object)
    if not isinstance(document, dict) or not isinstance(document.get("paths"), dict) or "openapi" not in document:
        raise ValueError(f"Not an OpenAPI document: {path}")
    return json.dumps(document, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Compare the complete generated OpenAPI document with its snapshot.")
    parser.add_argument("--schema", required=True, type=Path)
    parser.add_argument("--snapshot", default=SNAPSHOT, type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--update", action="store_true")
    arguments = parser.parse_args(argv)
    report = {
        "schema": str(arguments.schema),
        "snapshot": str(arguments.snapshot),
        "updated": False,
    }
    result = 1
    try:
        current = canonical_document(arguments.schema)
        report["generated_sha256"] = hashlib.sha256(current.encode()).hexdigest()
        if arguments.update:
            arguments.snapshot.parent.mkdir(parents=True, exist_ok=True)
            arguments.snapshot.write_text(current)
            report.update(updated=True, matches=True)
            print(f"Updated OpenAPI snapshot: {arguments.snapshot}")
            result = 0
        else:
            expected = canonical_document(arguments.snapshot)
            report["snapshot_sha256"] = hashlib.sha256(expected.encode()).hexdigest()
            report["matches"] = current == expected
            if current == expected:
                print("The complete generated OpenAPI document matches its committed snapshot.")
                result = 0
            else:
                difference = list(
                    difflib.unified_diff(
                        expected.splitlines(),
                        current.splitlines(),
                        fromfile="snapshot",
                        tofile="generated",
                        lineterm="",
                    )
                )
                report["difference"] = difference
                print(
                    "The OpenAPI snapshot is stale. Review the complete schema change, "
                    "then run make update-api-schema.",
                    file=sys.stderr,
                )
                print("\n".join(difference[:80]), file=sys.stderr)
    except (OSError, ValueError) as error:
        report["error"] = str(error)
        print(f"Cannot compare the OpenAPI snapshot: {error}", file=sys.stderr)
    if arguments.report:
        arguments.report.parent.mkdir(parents=True, exist_ok=True)
        arguments.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return result


if __name__ == "__main__":
    sys.exit(main())
