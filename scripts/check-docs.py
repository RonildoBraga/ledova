#!/usr/bin/env python3
"""Fail when the documentation disagrees with the tree it describes.

The rule and its scope are stated in docs/GATES.md under "The documentation
gate". This script is the mechanical half of that rule; keep the two in step.

Every other gate here protects source from drifting away from a rule. This one
protects the documents, because they drifted and nothing said so: an audit found
a register feature three documents called unbuilt, a schedule table missing seven
periodic tasks - two of which exist only to delete personal data on a retention
clock - a gate list that said three while make check ran eight, and a link whose
destination was wrapped onto a second line, which markdown does not join, so it
had been rendering as literal text.

Three rules, each decidable from the files alone:

dead-link      every relative link and #anchor in the documented set resolves.
periodic-task  the schedule table in OPERATIONS.md is exactly the set of
               @app.periodic tasks in backend/.
gate-list      every scripts/check-* script has a section in GATES.md, and
               every section names a script that exists.

All three are checked in BOTH directions, which is the property that makes them
worth having. A list that only refuses removals still lets a new thing go
undocumented, and the symptom is identical in both cases: a green line reporting
a number that looks like coverage and is a numerator. That is the same argument
check-comments.py makes for NOT_SCANNED and check-type-check.py makes for
NOT_A_WORKSPACE, applied to prose.

What it does not cover. It compares names and paths, never claims: a table row
that names the right task with the wrong schedule passes, and so does a
paragraph that describes a function's behaviour incorrectly. Those need a reader.
The point is narrower - that a thing which exists is mentioned, and a thing
mentioned exists - and that is exactly the class of drift the audit found most of.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

DOCUMENTS = ("README.md", "CONTRIBUTING.md", "SECURITY.md", "CODE_OF_CONDUCT.md")
DOC_DIR = "docs"

BACKEND = "backend"
OPERATIONS = "docs/OPERATIONS.md"
GATES = "docs/GATES.md"
SCRIPT_GLOB = "check-*"

PERIODIC = re.compile(r"@app\.periodic\(\s*cron\s*=\s*[\"']([^\"']+)[\"']")
DEFINITION = re.compile(r"^\s*def\s+(\w+)")
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*$")
BACKTICKED = re.compile(r"`([^`\n]+)`")

SCHEDULE_HEADING = "## Background jobs"
GATE_TABLE_HEADING = "## Every gate, and where its rule is written"

# A script that is deliberately not a gate: it is tooling the gates and the
# Makefile call, not a rule anything is held to, so GATES.md has no section for
# it and should not grow one.
NOT_A_GATE = {
    "check-port-free": "Makefile plumbing: refuses to start the chain test when its port is taken.",
}


def documented_files() -> list[Path]:
    files = [REPO_ROOT / name for name in DOCUMENTS]
    files += sorted((REPO_ROOT / DOC_DIR).glob("*.md"))
    return [path for path in files if path.exists()]


def slug(heading: str) -> str:
    text = heading.strip().lower()
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[^\w\s-]", "", text)
    # Each space becomes a hyphen, rather than each run of them. "Phase 2 -
    # Eligibility" loses its dash and keeps both spaces, so the anchor GitHub
    # serves carries two hyphens; collapsing whitespace here would report every
    # such heading as a dead anchor while the rendered page is fine.
    return text.strip().replace(" ", "-")


def anchors_of(path: Path) -> set[str]:
    found = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        heading = HEADING.match(line)
        if heading:
            found.add(slug(heading.group(1)))
    return found


def dead_links(files: list[Path]) -> list[str]:
    anchors = {path: anchors_of(path) for path in files}
    findings = []
    for path in files:
        relative = path.relative_to(REPO_ROOT)
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for target in LINK.findall(line):
                if target.startswith(("http://", "https://", "mailto:")):
                    continue
                if target.startswith("#"):
                    if target[1:] not in anchors[path]:
                        findings.append(f"{relative}:{line_number} dead anchor {target}")
                    continue
                location, _, fragment = target.partition("#")
                resolved = (path.parent / location).resolve()
                if not resolved.exists():
                    findings.append(f"{relative}:{line_number} missing file {location}")
                elif fragment and resolved in anchors and fragment not in anchors[resolved]:
                    findings.append(f"{relative}:{line_number} dead anchor {target}")
    return findings


def periodic_tasks() -> dict[str, str]:
    tasks = {}
    for path in sorted((REPO_ROOT / BACKEND).rglob("*.py")):
        if "tests" in path.parts or "migrations" in path.parts:
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            cron = PERIODIC.search(line)
            if not cron:
                continue
            for following in lines[index : index + 8]:
                name = DEFINITION.match(following)
                if name:
                    tasks[name.group(1)] = cron.group(1)
                    break
    return tasks


def scheduled_in_operations() -> set[str]:
    text = (REPO_ROOT / OPERATIONS).read_text(encoding="utf-8")
    start = text.find(SCHEDULE_HEADING)
    if start == -1:
        return set()
    named = set()
    for line in text[start:].splitlines():
        if not line.startswith("|"):
            if named:
                break
            continue
        for quoted in BACKTICKED.findall(line):
            named.add(quoted.strip().split(".")[-1].strip("`"))
    return named


def periodic_findings() -> list[str]:
    actual = periodic_tasks()
    documented = scheduled_in_operations()
    findings = []
    for name in sorted(set(actual) - documented):
        findings.append(f"{OPERATIONS}: periodic task `{name}` ({actual[name]}) is in no schedule row")
    for name in sorted(documented - set(actual)):
        findings.append(f"{OPERATIONS}: schedule names `{name}`, which is not an @app.periodic task")
    return findings


def gate_scripts() -> set[str]:
    found = set()
    for path in sorted((REPO_ROOT / "scripts").glob(SCRIPT_GLOB)):
        if path.is_file() and path.suffix in {".py", ".mjs"}:
            found.add(path.stem)
    return found


def gates_documented() -> set[str]:
    # The index table is the list, not the prose around it. Reading every
    # check-* name in the file instead was the first shape of this rule, and it
    # could not tell a script from `make check-mobile-test-awaits`, which is a
    # Makefile target, or from the route `batch-check-balances` wrapped so that
    # its second half opened a line. The table is what GATES.md declares this
    # rule holds it to, so the table is what it reads.
    text = (REPO_ROOT / GATES).read_text(encoding="utf-8")
    start = text.find(GATE_TABLE_HEADING)
    if start == -1:
        return set()
    named = set()
    for line in text[start:].splitlines():
        if not line.startswith("|"):
            if named:
                break
            continue
        first = line.strip("|").split("|")[0].strip().strip("`")
        if first.startswith("check-"):
            named.add(Path(first).stem)
    return named


def gate_findings() -> list[str]:
    scripts = gate_scripts()
    documented = gates_documented()
    findings = []
    for name in sorted(scripts - documented - set(NOT_A_GATE)):
        findings.append(f"{GATES}: scripts/{name} is a gate with no section")
    for name in sorted(documented - scripts):
        if name in NOT_A_GATE:
            continue
        findings.append(f"{GATES}: names scripts/{name}, which does not exist")
    for name in sorted(set(NOT_A_GATE) & documented):
        findings.append(
            f"{GATES}: documents scripts/{name}, which NOT_A_GATE says is not a gate"
            f" - {NOT_A_GATE[name]} Remove it from one list or the other."
        )
    return findings


def scan() -> tuple[list[str], int]:
    files = documented_files()
    findings = dead_links(files) + periodic_findings() + gate_findings()
    return findings, len(files)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--explain", action="store_true")
    arguments = parser.parse_args()

    if arguments.explain:
        tasks = periodic_tasks()
        print(f"Documents scanned ({len(documented_files())}):")
        for path in documented_files():
            print(f"  {path.relative_to(REPO_ROOT)}")
        print(f"\nPeriodic tasks in {BACKEND}/ ({len(tasks)}):")
        for name, cron in sorted(tasks.items(), key=lambda item: item[1]):
            print(f"  {cron:15} {name}")
        print(f"\nGate scripts ({len(gate_scripts())}): {', '.join(sorted(gate_scripts()))}")
        print(f"Not a gate ({len(NOT_A_GATE)}): {', '.join(sorted(NOT_A_GATE))}")
        return 0

    findings, scanned = scan()

    if findings:
        print(f"The documentation disagrees with the tree ({len(findings)}):\n", file=sys.stderr)
        for finding in findings:
            print(f"  {finding}", file=sys.stderr)
        print(
            "\nEach of these is a thing that exists and is undocumented, or is documented"
            "\nand does not exist. Fix the document, or the tree, or say which list it"
            "\nbelongs on - do not silence the finding."
            '\n\nThe rule and its scope are in docs/GATES.md, "The documentation gate".',
            file=sys.stderr,
        )
        return 1

    print(
        f"Documentation agrees with the tree: {scanned} documents, "
        f"{len(periodic_tasks())} periodic tasks, {len(gate_scripts())} gate scripts."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
