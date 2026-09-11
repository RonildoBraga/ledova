import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

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
        return SCOPE.native_scope(
            event,
            {"pull_request": {"base": {"sha": base or self.base}, "head": {"sha": head}}},
            self.repository,
        )

    def test_backend_and_docs_additions_modifications_deletions_skip(self):
        head = self.commit({"backend/new.py": "new", "docs/guide.md": "updated"}, removed=("backend/base.py",))
        self.assertEqual(self.decision(head)["required"], False)
        self.assertEqual(self.decision(head)["changed_files"], 3)

    def test_config_native_and_unknown_inputs_run_both_platforms(self):
        paths = (
            "package.json",
            "package-lock.json",
            "dashboard/package.json",
            ".gitattributes",
            ".npmrc",
            "packages/shared/src/index.ts",
            "mobile/assets/icon.png",
            "mobile/app.json",
            "mobile/plugins/withMobileSecurity.cjs",
            "mobile/native-tests/index.tsx",
            "scripts/native-build-scope.py",
            ".github/workflows/mobile-native.yml",
            "new-input/file.txt",
            "backend-other/file.py",
            "README.md",
        )
        for path in paths:
            with self.subTest(path=path):
                head = self.commit({path: "changed"})
                self.assertTrue(self.decision(head)["required"])
                self.git("reset", "--hard", self.base)

    def test_rename_from_mobile_to_docs_includes_removed_native_input(self):
        head = self.commit({"docs/retired.ts": "app"}, removed=("mobile/app.ts",))
        self.assertTrue(self.decision(head)["required"])
        self.assertEqual(self.decision(head)["changed_files"], 2)

    def test_rename_from_docs_to_mobile_runs_native(self):
        head = self.commit({"mobile/guide.ts": "guide"}, removed=("docs/guide.md",))
        self.assertTrue(self.decision(head)["required"])

    def test_native_deletion_runs_native(self):
        head = self.commit({}, removed=("mobile/app.ts",))
        self.assertTrue(self.decision(head)["required"])

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

    def test_main_push_and_manual_dispatch_run_even_for_unrelated_diff(self):
        head = self.commit({"backend/base.py": "updated"})
        self.assertFalse(self.decision(head)["required"])
        for event in ("push", "workflow_dispatch", "unknown", None):
            with self.subTest(event=event):
                self.assertTrue(self.decision(head, event=event)["required"])

    def test_missing_revision_empty_diff_and_invalid_event_run_native(self):
        for head in ("0" * 40, "not-a-revision", self.base):
            with self.subTest(head=head):
                self.assertTrue(self.decision(head)["required"])
        for payload in (None, [], {}, {"pull_request": {"base": None}}):
            with self.subTest(payload=payload):
                self.assertTrue(SCOPE.native_scope("pull_request", payload, self.repository)["required"])

    def test_base_advancement_outside_head_requires_native(self):
        head = self.commit({"backend/base.py": "updated"})
        self.git("checkout", "--detach", self.base)
        advanced_base = self.commit({"mobile/app.ts": "new base"})
        self.assertTrue(self.decision(head, base=advanced_base)["required"])

    def test_route_cli_writes_only_the_boolean_output(self):
        head = self.commit({"docs/new.md": "guide"})
        event = self.repository / "event.json"
        event.write_text(json.dumps({"pull_request": {"base": {"sha": self.base}, "head": {"sha": head}}}))
        output = self.repository / "github-output"
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "route",
                "--event",
                "pull_request",
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
