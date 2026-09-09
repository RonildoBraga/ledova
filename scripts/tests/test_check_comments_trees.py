#!/usr/bin/env python3
"""Hold the comment gate's tree list and GATES.md's to each other.

#185 added mobile/scripts to TREES and the prose kept describing the old set.
The section had already asked its readers to "change it and this section
together", which is an instruction rather than a mechanism, so nothing failed.
This asserts set equality in both directions: a tree added to the gate and not
to the sentence fails, and so does a tree named in the sentence that the gate
does not read.
"""

from __future__ import annotations

import importlib.util
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "scripts" / "check-comments.py"
DOCUMENT = ROOT / "docs" / "GATES.md"

_spec = importlib.util.spec_from_file_location("check_comments", SCRIPT)
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)

SENTENCE = re.compile(r"^The trees are, in full: (.+?)\.$", re.MULTILINE | re.DOTALL)


def documented_trees():
    text = DOCUMENT.read_text()
    match = SENTENCE.search(text)
    if match is None:
        raise AssertionError(
            f"{DOCUMENT.relative_to(ROOT)} has no 'The trees are, in full:' sentence for the comment gate."
        )
    return frozenset(re.findall(r"`([^`]+)`", match.group(1)))


class DocumentedTreesMatchTheGate(unittest.TestCase):
    def test_the_sentence_and_TREES_name_the_same_trees(self):
        self.assertEqual(documented_trees(), frozenset(tree for tree, _, _ in gate.TREES))

    def test_the_sentence_is_found_and_is_not_empty(self):
        self.assertGreater(len(documented_trees()), 0)

    def test_every_documented_tree_exists_in_the_repository(self):
        for tree in sorted(documented_trees()):
            self.assertTrue((ROOT / tree).is_dir(), f"{tree} is documented but is not a directory")


class EverySourceFileIsReachedByATree(unittest.TestCase):

    def test_native_templates_are_scanned_and_do_not_treat_urls_as_comments(self):
        source = ROOT / "mobile/plugins/native/LedovaHTTPRequestHandler.m"
        scanned = {
            path.resolve() for tree, extensions, recurse in gate.TREES for path in gate.files_in(tree, extensions, recurse)
        }
        self.assertIn(source, scanned)
        scanner = gate.FINDERS[source.suffix]
        self.assertEqual(scanner('#import <React/RCTHTTPRequestHandler.h>\n#if DEBUG\nNSString *url = @"http://localhost/";\n#endif\n'), [])
        self.assertEqual(scanner('NSString *url = @"https://localhost/"; // forbidden\n'), [(1, '// forbidden', False)])

    def test_nothing_is_outside_the_trees_without_a_stated_reason(self):
        scanned = {
            path.resolve() for tree, extensions, recurse in gate.TREES for path in gate.files_in(tree, extensions, recurse)
        }

        self.assertEqual(gate.unscanned_source_files(scanned), [])

    def test_every_exemption_states_a_reason(self):
        for path, reason in gate.NOT_SCANNED.items():
            with self.subTest(path=path):
                self.assertGreater(len(reason), 40, f"{path} needs a reason, not a label")

    def test_dropping_a_tree_leaves_its_files_unreached(self):
        without_backend = {
            path.resolve()
            for tree, extensions, recurse in gate.TREES
            if tree != "backend"
            for path in gate.files_in(tree, extensions, recurse)
        }

        self.assertGreater(len(gate.unscanned_source_files(without_backend)), 500)


class AnExemptionCoversWhatItNamesAndNothingElse(unittest.TestCase):

    def test_a_stated_path_exempts_the_tree_under_it(self):
        self.assertTrue(gate._exempt("scripts/check-comments.py"))
        self.assertTrue(gate._exempt("dashboard/tests/smoke/login.spec.ts"))

    def test_a_sibling_whose_name_starts_the_same_is_not_exempt(self):
        self.assertFalse(gate._exempt("scripts-extra/thing.ts"))
        self.assertFalse(gate._exempt("dashboard/tests/smoketest.ts"))

    def test_every_stated_exemption_is_a_path_that_exists(self):
        for stated in gate.NOT_SCANNED:
            with self.subTest(path=stated):
                self.assertTrue((ROOT / stated).exists(), f"{stated} is exempt from a gate it no longer meets")


class GeneratedOutputIsInvisibleRatherThanExempted(unittest.TestCase):

    PROBE = ROOT / "contracts" / "typechain-types" / "__gate_probe__.ts"

    def test_a_file_git_ignores_is_not_a_source_file_the_gate_can_see(self):
        self.PROBE.parent.mkdir(parents=True, exist_ok=True)
        self.PROBE.write_text("export const probe = 1;\n")
        self.addCleanup(self.PROBE.unlink, missing_ok=True)
        self.addCleanup(gate.tracked_files.cache_clear)
        gate.tracked_files.cache_clear()

        self.assertNotIn(self.PROBE, gate.tracked_files())
        self.assertEqual(gate.unscanned_source_files(set()), gate.unscanned_source_files({self.PROBE.resolve()}))

    def test_the_probe_would_be_seen_if_git_did_not_ignore_it(self):
        visible = ROOT / "contracts" / "__gate_probe__.ts"
        visible.write_text("export const probe = 1;\n")
        self.addCleanup(visible.unlink, missing_ok=True)
        self.addCleanup(gate.tracked_files.cache_clear)
        gate.tracked_files.cache_clear()

        self.assertIn(visible, gate.tracked_files())


if __name__ == "__main__":
    unittest.main()
