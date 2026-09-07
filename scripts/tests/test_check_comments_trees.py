#!/usr/bin/env python3
"""Hold the comment gate's tree list and ARCHITECTURE.md's to each other.

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
DOCUMENT = ROOT / "docs" / "ARCHITECTURE.md"

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


if __name__ == "__main__":
    unittest.main()


class EverySourceFileIsReachedByATree(unittest.TestCase):

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
