#!/usr/bin/env python3
"""Prove the type-check gate agrees with tsc about which configs examine nothing.

Every case in TruthTableFromTsc was run through the real compiler first, by
type-checking a file with a known error under that config and recording whether
the error surfaced. The gate has to reproduce those answers; a case that drifts
from the compiler is the gate becoming a second opinion instead of a check.
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "check-type-check.py"
_spec = importlib.util.spec_from_file_location("check_type_check", SCRIPT)
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)

REFERENCES = [{"path": "./nowhere"}]


class _Workspace(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.root = Path(self._directory.name)
        self.addCleanup(self._directory.cleanup)
        gate.ROOT = self.root

    def write(self, name: str, config: dict | str) -> Path:
        path = self.root / name
        path.write_text(config if isinstance(config, str) else json.dumps(config))
        return path


class TruthTableFromTsc(_Workspace):
    """Each expectation was measured against tsc before it was written here."""

    def test_empty_files_with_references_examines_nothing(self):
        config = self.write("a.json", {"files": [], "references": REFERENCES})
        self.assertTrue(gate.examines_nothing(config))

    def test_empty_files_beside_an_empty_include_examines_nothing(self):
        config = self.write("b.json", {"files": [], "include": [], "references": REFERENCES})
        self.assertTrue(gate.examines_nothing(config))

    def test_an_empty_include_alone_examines_nothing(self):
        config = self.write("c.json", {"include": [], "references": REFERENCES})
        self.assertTrue(gate.examines_nothing(config))

    def test_references_without_a_file_set_examines_everything(self):
        config = self.write("d.json", {"references": REFERENCES})
        self.assertFalse(gate.examines_nothing(config))

    def test_an_include_beside_empty_files_examines_everything(self):
        config = self.write("e.json", {"files": [], "include": ["**/*"], "references": REFERENCES})
        self.assertFalse(gate.examines_nothing(config))

    def test_an_inherited_empty_files_examines_nothing(self):
        self.write("base.json", {"files": []})
        config = self.write("f.json", {"extends": "./base.json", "references": REFERENCES})
        self.assertTrue(gate.examines_nothing(config))


class InheritanceStopsAtALocalFileSet(_Workspace):

    def test_a_local_include_overrides_an_inherited_empty_files(self):
        self.write("base.json", {"files": []})
        config = self.write("child.json", {"extends": "./base.json", "include": ["src"]})
        self.assertFalse(gate.examines_nothing(config))

    def test_a_local_include_means_an_unresolvable_base_is_never_consulted(self):
        config = self.write("child.json", {"extends": "not-installed/tsconfig", "include": ["src"]})
        self.assertFalse(gate.examines_nothing(config))

    def test_the_extension_may_be_left_off(self):
        self.write("base.json", {"files": []})
        config = self.write("child.json", {"extends": "./base", "references": REFERENCES})
        self.assertTrue(gate.examines_nothing(config))

    def test_each_key_of_an_extends_array_resolves_independently(self):
        """Measured: tsc type-checks src in either order, so "files" does not veto "include"."""
        self.write("first.json", {"include": ["src"]})
        self.write("second.json", {"files": []})

        for order in (["./first.json", "./second.json"], ["./second.json", "./first.json"]):
            with self.subTest(order=order):
                config = self.write("child.json", {"extends": order})
                self.assertFalse(gate.examines_nothing(config))

    def test_an_inherited_file_set_survives_a_local_empty_include(self):
        self.write("base.json", {"files": ["a.ts"]})
        config = self.write("child.json", {"extends": "./base.json", "include": []})
        self.assertFalse(gate.examines_nothing(config))


class UnreadableIsAFindingNotACrash(_Workspace):

    def test_a_base_that_cannot_be_found_is_reported(self):
        config = self.write("child.json", {"extends": "expo/tsconfig.base", "references": REFERENCES})
        with self.assertRaises(gate.Unreadable) as caught:
            gate.examines_nothing(config)
        self.assertIn("cannot find", str(caught.exception))

    def test_a_cycle_is_reported_rather_than_recursing(self):
        self.write("a.json", {"extends": "./b.json"})
        config = self.write("b.json", {"extends": "./a.json"})
        with self.assertRaises(gate.Unreadable) as caught:
            gate.examines_nothing(config)
        self.assertIn("cycle", str(caught.exception))

    def test_malformed_json_names_the_file(self):
        config = self.write("broken.json", '{"files": [,}')
        with self.assertRaises(gate.Unreadable) as caught:
            gate.examines_nothing(config)
        self.assertIn("broken.json", str(caught.exception))


class TsconfigIsJsonc(_Workspace):

    def test_a_block_comment_does_not_take_the_gate_down(self):
        config = self.write(
            "commented.json",
            '{\n  /* the real config lives in the referenced projects */\n'
            '  "files": [],\n  "references": [{"path": "./nowhere"}]\n}',
        )
        self.assertTrue(gate.examines_nothing(config))

    def test_a_line_comment_is_stripped(self):
        config = self.write(
            "commented.json",
            '{\n  // solution style\n  "files": [],\n  "references": [{"path": "./nowhere"}]\n}',
        )
        self.assertTrue(gate.examines_nothing(config))

    def test_a_trailing_comma_is_accepted(self):
        config = self.write(
            "trailing.json",
            '{\n  "files": [],\n  "references": [{"path": "./nowhere"}],\n}',
        )
        self.assertTrue(gate.examines_nothing(config))

    def test_a_url_inside_a_string_is_not_mistaken_for_a_comment(self):
        config = self.write(
            "url.json",
            '{"include": ["src"], "compilerOptions": {"paths": {"x": ["https://example.test/a"]}}}',
        )
        self.assertFalse(gate.examines_nothing(config))


class BuildModeDetection(unittest.TestCase):
    def matches(self, script):
        return bool(gate.BUILD_MODE.search(script))

    def test_plain_noemit_is_not_build_mode(self):
        self.assertFalse(self.matches("tsc --noEmit"))

    def test_short_and_long_build_flags_are_both_recognised(self):
        self.assertTrue(self.matches("tsc -b --noEmit"))
        self.assertTrue(self.matches("tsc --build --noEmit"))

    def test_the_flag_is_found_after_other_arguments(self):
        self.assertTrue(self.matches("tsc --noEmit -b"))

    def test_a_project_flag_is_not_build_mode(self):
        self.assertFalse(self.matches("tsc -p tsconfig.app.json --noEmit"))


if __name__ == "__main__":
    unittest.main()


class AWorkspaceNobodyDeclaredIsAFailure(_Workspace):

    def setUp(self):
        super().setUp()
        declared = gate.WORKSPACES
        exempt = dict(gate.NOT_A_WORKSPACE)
        self.addCleanup(setattr, gate, "WORKSPACES", declared)
        self.addCleanup(setattr, gate, "NOT_A_WORKSPACE", exempt)

    def _candidate(self, name):
        (self.root / name).mkdir(parents=True, exist_ok=True)
        (self.root / name / "package.json").write_text(json.dumps({"scripts": {"type-check": "tsc"}}))
        (self.root / name / "tsconfig.json").write_text(json.dumps({"include": ["src"]}))

    def test_a_directory_that_looks_like_a_workspace_and_is_not_listed_is_found(self):
        self._candidate("qa-console")
        gate.WORKSPACES = ()
        gate.NOT_A_WORKSPACE = {}

        self.assertEqual(gate.undeclared_workspaces(), ["qa-console"])

    def test_listing_it_settles_it(self):
        self._candidate("qa-console")
        gate.WORKSPACES = ("qa-console",)
        gate.NOT_A_WORKSPACE = {}

        self.assertEqual(gate.undeclared_workspaces(), [])

    def test_so_does_exempting_it_with_a_reason(self):
        self._candidate("qa-console")
        gate.WORKSPACES = ()
        gate.NOT_A_WORKSPACE = {"qa-console": "Not type-checked here."}

        self.assertEqual(gate.undeclared_workspaces(), [])

    def test_a_directory_without_a_tsconfig_is_not_a_candidate(self):
        (self.root / "docs-site").mkdir()
        (self.root / "docs-site" / "package.json").write_text(json.dumps({"scripts": {}}))
        gate.WORKSPACES = ()
        gate.NOT_A_WORKSPACE = {}

        self.assertEqual(gate.undeclared_workspaces(), [])

    def test_node_modules_is_not_searched(self):
        self._candidate("dashboard/node_modules/some-package")
        gate.WORKSPACES = ()
        gate.NOT_A_WORKSPACE = {}

        self.assertEqual(gate.undeclared_workspaces(), [])
