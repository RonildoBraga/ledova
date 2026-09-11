import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "native-build-scope.py"
SPEC = importlib.util.spec_from_file_location("native_build_scope", SCRIPT)
SCOPE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCOPE)


class NativeBuildScopeTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.repository = Path(directory.name)
        self.git("init", "--quiet")
        self.git("config", "maintenance.auto", "false")
        self.git("config", "diff.renames", "true")
        self.base = self.commit({"backend/base.py": "base", "docs/guide.md": "guide", "mobile/app.ts": "app"})

    def git(self, *arguments):
        return subprocess.run(
            ["git", "-c", "user.name=Native CI test", "-c", "user.email=ci@example.invalid", *arguments],
            cwd=self.repository,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def commit(self, files, removed=()):
        for relative in removed:
            (self.repository / relative).unlink()
        for relative, content in files.items():
            path = self.repository / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        self.git("add", "--all")
        self.git("commit", "--quiet", "--allow-empty", "-m", "Fixture")
        return self.git("rev-parse", "HEAD")

    def decision(self, head, base=None, event="pull_request"):
        base = self.base if base is None else base
        payload = (
            {"before": base, "after": head}
            if event == "push"
            else {"pull_request": {"base": {"sha": base}, "head": {"sha": head}}}
        )
        return SCOPE.native_scope(
            event,
            payload,
            self.repository,
        )

    def test_backend_and_docs_additions_modifications_deletions_skip(self):
        head = self.commit({"backend/new.py": "new", "docs/guide.md": "updated"}, removed=("backend/base.py",))
        self.assertEqual(self.decision(head)["required"], False)
        self.assertEqual(self.decision(head)["changed_files"], 3)

    def test_mobile_shared_and_build_inputs_run_both_platforms(self):
        paths = (
            "package.json",
            "package-lock.json",
            "npm-shrinkwrap.json",
            "dashboard/package.json",
            ".gitattributes",
            ".npmrc",
            "packages/shared/src/index.ts",
            "mobile/assets/icon.png",
            "mobile/app.json",
            "mobile/plugins/withMobileSecurity.cjs",
            "mobile/native-tests/index.tsx",
            "scripts/native-build-scope.py",
            "scripts/tests/test_native_build_scope.py",
            ".github/workflows/mobile-native.yml",
        )
        for path in paths:
            with self.subTest(path=path):
                head = self.commit({path: "changed"})
                self.assertTrue(self.decision(head)["required"])
                self.assertTrue(self.decision(head, event="push")["required"])
                self.git("reset", "--hard", self.base)

    def test_root_documentation_does_not_require_native_builds(self):
        head = self.commit({"README.md": "updated", "CONTRIBUTING.md": "updated", "docs/PRACTICES.md": "updated"})
        for event in ("pull_request", "push"):
            with self.subTest(event=event):
                self.assertFalse(self.decision(head, event=event)["required"])
                self.assertEqual(self.decision(head, event=event)["changed_files"], 3)

    def test_unrelated_paths_skip_without_partial_prefix_or_filename_matches(self):
        paths = (
            "backend/new.py",
            "dashboard/src/index.tsx",
            "dashboard/package-lock.json",
            "marketing/index.html",
            ".github/workflows/ci.yml",
            ".gitignore",
            "new-input/file.txt",
            "backend-other/file.py",
            "mobile-other/file.ts",
            "packages/shared-other/file.ts",
            "scripts/native-build-scope.py.txt",
            "nested/package.json",
        )
        for path in paths:
            with self.subTest(path=path):
                head = self.commit({path: "changed"})
                self.assertFalse(self.decision(head)["required"])
                self.assertFalse(self.decision(head, event="push")["required"])
                self.git("reset", "--hard", self.base)

    def test_rename_from_mobile_to_docs_includes_removed_native_input(self):
        head = self.commit({"docs/retired.ts": "app"}, removed=("mobile/app.ts",))
        self.assertTrue(self.decision(head)["required"])
        self.assertTrue(self.decision(head, event="push")["required"])
        self.assertEqual(self.decision(head)["changed_files"], 2)

    def test_rename_from_docs_to_mobile_runs_native(self):
        head = self.commit({"mobile/guide.ts": "guide"}, removed=("docs/guide.md",))
        self.assertTrue(self.decision(head)["required"])

    def test_native_deletion_runs_native(self):
        head = self.commit({}, removed=("mobile/app.ts",))
        self.assertTrue(self.decision(head)["required"])
        self.assertTrue(self.decision(head, event="push")["required"])

    def test_unrelated_rename_and_deletion_skip(self):
        head = self.commit({"README.md": "guide"}, removed=("docs/guide.md", "backend/base.py"))
        for event in ("pull_request", "push"):
            with self.subTest(event=event):
                self.assertFalse(self.decision(head, event=event)["required"])
                self.assertEqual(self.decision(head, event=event)["changed_files"], 3)

    def test_nul_delimited_unrelated_names_do_not_become_extra_paths(self):
        head = self.commit({"docs/a b\tc\nd.md": "unrelated"})
        self.assertFalse(self.decision(head)["required"])
        self.assertEqual(self.decision(head)["changed_files"], 1)

    def test_complete_diff_includes_native_change_after_three_hundred_files(self):
        files = {f"backend/file-{index:04}.py": "new" for index in range(301)}
        files["mobile/app.ts"] = "updated"
        head = self.commit(files)
        self.assertTrue(self.decision(head)["required"])
        self.assertEqual(self.decision(head)["changed_files"], 302)

    def test_push_compares_all_commits_including_earlier_mobile_changes(self):
        mobile_head = self.commit({"mobile/app.ts": "updated"})
        head = self.commit({"backend/base.py": "updated"})
        self.assertTrue(self.decision(head, event="push")["required"])
        self.assertEqual(self.decision(head, event="push").get("changed_files"), 2)
        self.assertFalse(self.decision(head, base=mobile_head, event="push")["required"])

    def test_push_with_only_unrelated_commits_skips(self):
        self.commit({"backend/base.py": "updated"})
        head = self.commit({"dashboard/src/index.ts": "new"})
        self.assertFalse(self.decision(head, event="push")["required"])
        self.assertEqual(self.decision(head, event="push")["changed_files"], 2)

    def test_manual_dispatch_and_unknown_events_run_even_for_unrelated_diff(self):
        head = self.commit({"backend/base.py": "updated"})
        self.assertFalse(self.decision(head)["required"])
        for event in ("workflow_dispatch", "unknown", "pull_request_target", None):
            with self.subTest(event=event):
                self.assertTrue(self.decision(head, event=event)["required"])

    def test_verified_empty_diff_skips(self):
        empty_head = self.commit({})
        for event in ("pull_request", "push"):
            for head in (self.base, empty_head):
                with self.subTest(event=event, head=head):
                    self.assertFalse(self.decision(head, event=event)["required"])
                    self.assertEqual(self.decision(head, event=event)["changed_files"], 0)

    def test_invalid_zero_missing_or_noncommit_revisions_require_native(self):
        tree = self.git("rev-parse", "HEAD^{tree}")
        blob = self.git("rev-parse", "HEAD:mobile/app.ts")
        revisions = ("0" * 40, "f" * 40, "not-a-revision", "", 12, [], {}, tree, blob)
        for event in ("pull_request", "push"):
            for revision in revisions:
                with self.subTest(event=event, revision=revision):
                    self.assertTrue(self.decision(revision, event=event)["required"])
                    self.assertTrue(self.decision(self.base, base=revision, event=event)["required"])

    def test_malformed_payload_requires_native(self):
        payloads = (
            None,
            [],
            {},
            {"pull_request": {"base": None}},
            {"before": self.base},
            {"after": self.base},
            {"before": None, "after": self.base},
            {"before": self.base, "after": None},
        )
        for event in ("pull_request", "push"):
            for payload in payloads:
                with self.subTest(event=event, payload=payload):
                    self.assertTrue(SCOPE.native_scope(event, payload, self.repository)["required"])

    def test_malformed_diff_evidence_requires_native(self):
        for diff in (b"docs/file", b"\0", b"/file\0", b"docs//file\0", b"docs/../file\0", b"./file\0", b"\xff\0"):
            with self.subTest(diff=diff):
                results = (
                    subprocess.CompletedProcess([], 0),
                    subprocess.CompletedProcess([], 0, stdout=diff),
                )
                with patch.object(SCOPE.subprocess, "run", side_effect=results):
                    self.assertTrue(self.decision(self.base)["required"])

    def test_base_advancement_outside_head_requires_native(self):
        head = self.commit({"backend/base.py": "updated"})
        self.git("checkout", "--detach", self.base)
        advanced_base = self.commit({"mobile/app.ts": "new base"})
        self.assertTrue(self.decision(head, base=advanced_base)["required"])
        self.assertTrue(self.decision(head, base=advanced_base, event="push")["required"])

    def test_reversed_push_history_requires_native(self):
        head = self.commit({"backend/base.py": "updated"})
        self.assertTrue(self.decision(self.base, base=head, event="push")["required"])

    def test_shallow_history_requires_native_until_base_comparison_is_available(self):
        head = self.commit({"backend/base.py": "updated"})
        with tempfile.TemporaryDirectory() as directory:
            clone = Path(directory) / "clone"
            subprocess.run(
                ["git", "clone", "--quiet", "--depth", "1", self.repository.as_uri(), str(clone)],
                check=True,
                capture_output=True,
            )
            payloads = (
                ("pull_request", {"pull_request": {"base": {"sha": self.base}, "head": {"sha": head}}}),
                ("push", {"before": self.base, "after": head}),
            )
            for event, payload in payloads:
                with self.subTest(event=event):
                    self.assertTrue(SCOPE.native_scope(event, payload, clone)["required"])
            subprocess.run(["git", "fetch", "--quiet", "--deepen=1"], cwd=clone, check=True, capture_output=True)
            for event, payload in payloads:
                with self.subTest(event=event):
                    self.assertFalse(SCOPE.native_scope(event, payload, clone)["required"])

    def test_route_cli_writes_only_the_boolean_output(self):
        head = self.commit({"docs/new.md": "guide"})
        events = (
            ("pull_request", {"pull_request": {"base": {"sha": self.base}, "head": {"sha": head}}}),
            ("push", {"before": self.base, "after": head}),
        )
        for event_name, payload in events:
            with self.subTest(event=event_name):
                event = self.repository / f"{event_name}-event.json"
                event.write_text(json.dumps(payload))
                output = self.repository / f"{event_name}-github-output"
                result = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPT),
                        "route",
                        "--event",
                        event_name,
                        "--event-file",
                        str(event),
                        "--repository",
                        str(self.repository),
                    ],
                    env={**os.environ, "GITHUB_OUTPUT": str(output)},
                    check=True,
                    capture_output=True,
                    text=True,
                )
                self.assertFalse(json.loads(result.stdout)["required"])
                self.assertEqual(output.read_text(), "required=false\n")


class NativeBuildVerdictTest(unittest.TestCase):
    def needs(self, required="true", routing="success", android="success", ios="success"):
        return {
            "scope": {"result": routing, "outputs": {"required": required}},
            "android": {"result": android},
            "ios": {"result": ios},
        }

    def test_required_builds_and_intentional_skips_both_have_positive_controls(self):
        self.assertTrue(SCOPE.native_verdict(self.needs()))
        self.assertTrue(SCOPE.native_verdict(self.needs(required="false", android="skipped", ios="skipped")))

    def test_routing_failure_cancellation_missing_and_invalid_output_cannot_pass(self):
        for routing in ("failure", "cancelled", "skipped", ""):
            with self.subTest(routing=routing):
                self.assertFalse(SCOPE.native_verdict(self.needs(routing=routing)))
                self.assertFalse(
                    SCOPE.native_verdict(
                        self.needs(required="false", routing=routing, android="skipped", ios="skipped")
                    )
                )
        for required in (None, True, "", "FALSE", "maybe"):
            with self.subTest(required=required):
                self.assertFalse(SCOPE.native_verdict(self.needs(required=required)))
                self.assertFalse(SCOPE.native_verdict(self.needs(required=required, android="skipped", ios="skipped")))
        for needs in (None, [], {}, {"scope": {"result": "success", "outputs": None}}):
            with self.subTest(needs=needs):
                self.assertFalse(SCOPE.native_verdict(needs))

    def test_either_native_job_failure_cancellation_or_unexpected_skip_cannot_pass(self):
        for platform in ("android", "ios"):
            for result in ("failure", "cancelled", "skipped", ""):
                with self.subTest(platform=platform, result=result):
                    self.assertFalse(SCOPE.native_verdict(self.needs(**{platform: result})))

    def test_skip_decision_with_unexpected_job_results_cannot_pass(self):
        self.assertFalse(SCOPE.native_verdict(self.needs(required="false")))

    def test_verdict_cli_exits_nonzero_on_invalid_or_failed_dependency_results(self):
        for needs in ("not-json", json.dumps(self.needs(ios="failure"))):
            with self.subTest(needs=needs):
                result = subprocess.run(
                    [sys.executable, str(SCRIPT), "verdict"],
                    env={**os.environ, "NATIVE_JOB_RESULTS": needs},
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 1)


if __name__ == "__main__":
    unittest.main()
