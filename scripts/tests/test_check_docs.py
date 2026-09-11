#!/usr/bin/env python3
"""Prove the documentation gate fires, and on the right things.

A gate that reports zero because its pattern stopped matching looks exactly like
a gate that reports zero because the documents are correct. Every test here
plants something, and each rule is planted in both directions: a thing that
exists and is undocumented, and a thing documented that does not exist.

Two of these are calibrations rather than plants. Both shapes reported the real
tree as broken while the rendered page and the Makefile were fine, and both stay
here so the fix cannot be undone quietly.
"""

from __future__ import annotations

import contextlib
import importlib.util
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check-docs.py"
_spec = importlib.util.spec_from_file_location("check_docs", SCRIPT)
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)

TABLE_HEADING = gate.GATE_TABLE_HEADING
SCHEDULE_HEADING = gate.SCHEDULE_HEADING


@contextlib.contextmanager
def a_tree(documents: dict[str, str], scripts: tuple[str, ...] = ()):
    """Point the gate at a synthetic repository and give it back afterwards."""
    with TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "docs").mkdir()
        (root / "scripts").mkdir()
        (root / "backend").mkdir()
        for name, text in documents.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        for name in scripts:
            (root / "scripts" / name).write_text("", encoding="utf-8")
        original = gate.REPO_ROOT
        gate.REPO_ROOT = root
        try:
            yield root
        finally:
            gate.REPO_ROOT = original


def a_backend_task(root: Path, module: str, cron: str, name: str) -> None:
    path = root / "backend" / module
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'@app.periodic(cron="{cron}")\n@app.task\ndef {name}(timestamp: int = 0):\n    return None\n',
        encoding="utf-8",
    )


def a_gates_file(rows: str) -> str:
    return f"{TABLE_HEADING}\n\n| Script | Rule |\n| --- | --- |\n{rows}\n\nProse after it.\n"


def a_schedule(rows: str) -> str:
    return f"{SCHEDULE_HEADING}\n\n| Schedule | Task |\n| --- | --- |\n{rows}\n\nProse after it.\n"


class TheDeadLinkRuleSeesBothDirections(unittest.TestCase):

    def test_a_link_to_a_missing_file_is_a_finding(self):
        with a_tree({"README.md": "See [operations](docs/OPERATIONS.md).\n"}):
            findings = gate.dead_links(gate.documented_files())
        self.assertEqual(len(findings), 1)
        self.assertIn("missing file docs/OPERATIONS.md", findings[0])

    def test_a_link_to_a_heading_that_does_not_exist_is_a_finding(self):
        with a_tree({"README.md": "# Title\n\nSee [later](#no-such-heading).\n"}):
            findings = gate.dead_links(gate.documented_files())
        self.assertEqual(len(findings), 1)
        self.assertIn("dead anchor #no-such-heading", findings[0])

    def test_a_link_into_another_document_checks_that_documents_headings(self):
        documents = {
            "README.md": "See [jobs](docs/OPERATIONS.md#background-jobs).\n",
            "docs/OPERATIONS.md": "## Something else\n",
        }
        with a_tree(documents):
            findings = gate.dead_links(gate.documented_files())
        self.assertEqual(len(findings), 1)
        self.assertIn("dead anchor docs/OPERATIONS.md#background-jobs", findings[0])

    def test_a_link_that_resolves_is_not_a_finding(self):
        documents = {
            "README.md": "See [jobs](docs/OPERATIONS.md#background-jobs).\n",
            "docs/OPERATIONS.md": "## Background jobs\n",
        }
        with a_tree(documents):
            self.assertEqual(gate.dead_links(gate.documented_files()), [])

    def test_an_external_url_is_not_resolved(self):
        with a_tree({"README.md": "See [the act](https://example.invalid/a#b).\n"}):
            self.assertEqual(gate.dead_links(gate.documented_files()), [])

    def test_a_heading_whose_punctuation_leaves_two_spaces_keeps_two_hyphens(self):
        """The calibration: an anchor turns each space into a hyphen, not each run.

        GitHub strips the dash from "Phase 2 - Eligibility" and keeps both
        surrounding spaces, so the anchor it serves carries two hyphens.
        Collapsing whitespace in the slug reported every such heading as dead
        while the rendered page was fine.
        """
        documents = {
            "README.md": "See [phase](docs/ROADMAP.md#phase-2--eligibility-and-the-register).\n",
            "docs/ROADMAP.md": "## Phase 2 — Eligibility and the register\n",
        }
        with a_tree(documents):
            self.assertEqual(gate.dead_links(gate.documented_files()), [])


class ThePeriodicTaskRuleSeesBothDirections(unittest.TestCase):

    def test_a_task_in_no_schedule_row_is_a_finding(self):
        with a_tree({"docs/OPERATIONS.md": a_schedule("| daily | `something_else` |")}) as root:
            a_backend_task(root, "tokens/tasks/fold.py", "20 */6 * * *", "fold_every_share_class")
            findings = gate.periodic_findings()
        self.assertEqual(len(findings), 2)
        self.assertIn("`fold_every_share_class` (20 */6 * * *) is in no schedule row", findings[0])

    def test_a_schedule_row_naming_no_task_is_a_finding(self):
        with a_tree({"docs/OPERATIONS.md": a_schedule("| daily | `a_task_that_was_deleted` |")}):
            findings = gate.periodic_findings()
        self.assertEqual(len(findings), 1)
        self.assertIn("which is not an @app.periodic task", findings[0])

    def test_a_documented_task_is_not_a_finding(self):
        with a_tree({"docs/OPERATIONS.md": a_schedule("| daily | `purge_the_thing` |")}) as root:
            a_backend_task(root, "users/tasks/retention.py", "0 3 * * *", "purge_the_thing")
            self.assertEqual(gate.periodic_findings(), [])

    def test_a_dotted_row_matches_on_the_task_name(self):
        row = "| daily | `offerings.expire_unpaid_subscriptions` |"
        with a_tree({"docs/OPERATIONS.md": a_schedule(row)}) as root:
            a_backend_task(root, "offerings/tasks/s.py", "0 3 * * *", "expire_unpaid_subscriptions")
            self.assertEqual(gate.periodic_findings(), [])

    def test_a_task_defined_under_tests_is_not_a_task(self):
        with a_tree({"docs/OPERATIONS.md": a_schedule("| daily | `nothing` |")}) as root:
            a_backend_task(root, "tokens/tests/test_fold.py", "0 3 * * *", "a_fixture_task")
            self.assertNotIn("a_fixture_task", " ".join(gate.periodic_findings()))


class TheGateListRuleSeesBothDirections(unittest.TestCase):

    def test_a_script_with_no_row_is_a_finding(self):
        documents = {"docs/GATES.md": a_gates_file("| `check-layers.py` | [Layers](#layers) |")}
        with a_tree(documents, scripts=("check-layers.py", "check-newly-added.py")):
            findings = gate.gate_findings()
        self.assertEqual(len(findings), 1)
        self.assertIn("scripts/check-newly-added is a gate with no section", findings[0])

    def test_a_row_naming_no_script_is_a_finding(self):
        documents = {"docs/GATES.md": a_gates_file("| `check-deleted.py` | [Gone](#gone) |")}
        with a_tree(documents, scripts=("check-layers.py",)):
            findings = gate.gate_findings()
        self.assertEqual(len(findings), 2)
        self.assertIn("names scripts/check-deleted, which does not exist", " ".join(findings))

    def test_a_documented_script_is_not_a_finding(self):
        documents = {"docs/GATES.md": a_gates_file("| `check-layers.py` | [Layers](#layers) |")}
        with a_tree(documents, scripts=("check-layers.py",)):
            self.assertEqual(gate.gate_findings(), [])

    def test_an_mjs_gate_counts_as_a_gate(self):
        documents = {"docs/GATES.md": a_gates_file("| `check-self-imports.mjs` | [Shared](#shared) |")}
        with a_tree(documents, scripts=("check-self-imports.mjs",)):
            self.assertEqual(gate.gate_findings(), [])

    def test_a_script_named_in_not_a_gate_needs_no_row(self):
        documents = {"docs/GATES.md": a_gates_file("| `check-layers.py` | [Layers](#layers) |")}
        with a_tree(documents, scripts=("check-layers.py", "check-port-free.py")):
            self.assertEqual(gate.gate_findings(), [])

    def test_documenting_a_not_a_gate_script_is_a_finding_from_the_other_side(self):
        rows = "| `check-layers.py` | [Layers](#layers) |\n| `check-port-free.py` | [Ports](#ports) |"
        with a_tree({"docs/GATES.md": a_gates_file(rows)}, scripts=("check-layers.py", "check-port-free.py")):
            findings = gate.gate_findings()
        self.assertEqual(len(findings), 1)
        self.assertIn("NOT_A_GATE says is not a gate", findings[0])

    def test_prose_naming_a_make_target_is_not_read_as_a_script(self):
        """The calibration: the list is the table, not the prose around it.

        Reading every check-* name in the file could not tell a script from
        `make check-mobile-test-awaits`, which is a Makefile target, or from the
        route `batch-check-balances` wrapped so its second half opened a line.
        """
        document = (
            a_gates_file("| `check-layers.py` | [Layers](#layers) |")
            + "\nRun `make check-mobile-test-awaits` too, and POST to batch-\n"
            + "check-balances for a preview.\n"
        )
        with a_tree({"docs/GATES.md": document}, scripts=("check-layers.py",)):
            self.assertEqual(gate.gate_findings(), [])


class TheGateRefusesToPassByFindingNothing(unittest.TestCase):

    def test_a_missing_gate_table_finds_every_script_rather_than_none(self):
        with a_tree({"docs/GATES.md": "# Gates\n\nNo table here.\n"}, scripts=("check-layers.py",)):
            findings = gate.gate_findings()
        self.assertEqual(len(findings), 1)
        self.assertIn("check-layers is a gate with no section", findings[0])

    def test_a_missing_schedule_table_finds_every_task_rather_than_none(self):
        with a_tree({"docs/OPERATIONS.md": "# Operations\n\nNo table here.\n"}) as root:
            a_backend_task(root, "tokens/tasks/fold.py", "0 3 * * *", "a_real_task")
            findings = gate.periodic_findings()
        self.assertEqual(len(findings), 1)
        self.assertIn("`a_real_task`", findings[0])

    def test_the_real_tree_passes(self):
        findings, scanned = gate.scan()
        self.assertEqual(findings, [], f"the documentation gate fails on the tree: {findings}")
        self.assertGreater(scanned, 5)


if __name__ == "__main__":
    unittest.main()
