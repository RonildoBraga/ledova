import json
import os
import shlex
import subprocess
import sys
from copy import deepcopy
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import yaml
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from shared.api.routes import PROVIDER_EXCLUSIONS
from shared.api.schema_environment import environment_drift, expected_environment


class SchemaEnvironmentTest(SimpleTestCase):
    def setUp(self):
        expected = expected_environment()
        self.measured = {
            "python": expected["python"],
            "settings": expected["settings"],
            "packages": expected["packages"],
            "database_vendor": "postgresql",
            "postgresql_version": expected["postgresql_major"] * 10000 + 4,
        }

    def test_the_recorded_toolchain_and_postgres_major_are_required(self):
        self.assertEqual(environment_drift(self.measured), [])
        for name, value in (
            ("python", "0.0.0"),
            ("settings", "ledova_backend.settings.test"),
            ("database_vendor", "sqlite"),
            ("postgresql_version", 0),
        ):
            with self.subTest(name=name):
                measured = deepcopy(self.measured)
                measured[name] = value
                self.assertTrue(environment_drift(measured))

    def test_missing_or_changed_generator_packages_fail(self):
        for name in self.measured["packages"]:
            with self.subTest(package=name):
                measured = deepcopy(self.measured)
                del measured["packages"][name]
                self.assertTrue(any(name in finding for finding in environment_drift(measured)))
                measured["packages"][name] = "0.0.0"
                self.assertTrue(any(name in finding for finding in environment_drift(measured)))

    def invoke(self, measured, paths, routes, pending=()):
        with TemporaryDirectory() as directory:
            schema = Path(directory) / "openapi.json"
            report = Path(directory) / "environment.json"

            def generate(*args, **kwargs):
                schema.write_text(json.dumps({"openapi": "3.0.3", "paths": paths}))

            command = "shared.management.commands.export_api_schema."
            with (
                patch(command + "measured_environment", return_value=measured),
                patch(command + "MigrationExecutor") as executor,
                patch(command + "call_command", side_effect=generate) as generator,
                patch(command + "registered_routes", return_value=routes),
            ):
                executor.return_value.migration_plan.return_value = pending
                error = None
                try:
                    call_command(
                        "export_api_schema",
                        file=schema,
                        report=report,
                        stdout=StringIO(),
                    )
                except CommandError as caught:
                    error = str(caught)
                return (
                    error,
                    generator.call_count,
                    json.loads(report.read_text()),
                    schema.exists(),
                )

    def test_wrong_environment_or_unapplied_migrations_refuse_before_generation(self):
        measured = deepcopy(self.measured)
        measured["database_vendor"] = "sqlite"
        error, calls, report, exists = self.invoke(measured, {}, set())
        self.assertIn("requires PostgreSQL", error)
        self.assertEqual(calls, 0)
        self.assertTrue(report["environment_findings"])
        self.assertFalse(exists)
        error, calls, _, exists = self.invoke(self.measured, {}, set(), pending=[object()])
        self.assertIn("Apply all migrations", error)
        self.assertEqual(calls, 0)
        self.assertFalse(exists)

    def test_generation_checks_current_routes_and_records_the_deliberate_exclusions(
        self,
    ):
        routes = PROVIDER_EXCLUSIONS | {("get", "/api/synthetic/")}
        paths = {"/api/synthetic/": {"get": {"responses": {"204": {"description": "Empty"}}}}}
        error, calls, report, exists = self.invoke(self.measured, paths, routes)
        self.assertIsNone(error)
        self.assertEqual(calls, 1)
        self.assertTrue(exists)
        self.assertEqual(report["route_findings"], [])
        self.assertEqual(
            report["provider_exclusions"],
            [list(route) for route in sorted(PROVIDER_EXCLUSIONS)],
        )
        error, _, report, exists = self.invoke(self.measured, {}, routes)
        self.assertIn("GET /api/synthetic/", error)
        self.assertTrue(exists)
        self.assertTrue(report["route_findings"])

    def invoke_ci_generation(self, valid):
        repository = Path(__file__).resolve().parents[3]
        workflow = yaml.safe_load((repository / ".github/workflows/ci.yml").read_text())
        job = next(
            job
            for job in workflow["jobs"].values()
            if any(step.get("id") == "generate-schema" for step in job.get("steps", []))
        )
        step = next(step for step in job["steps"] if step.get("id") == "generate-schema")
        shell = step.get(
            "shell",
            job.get("defaults", {})
            .get("run", {})
            .get("shell", workflow.get("defaults", {}).get("run", {}).get("shell")),
        )
        commands = {None: ["bash", "-e"], "bash": ["bash", "--noprofile", "--norc", "-eo", "pipefail"]}
        self.assertIn(shell, commands)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            launcher = root / "python"
            launcher.write_text(
                f'#!/bin/sh\nexec {shlex.quote(sys.executable)} -m shared.tests.schema_pipeline_worker "$@"\n'
            )
            launcher.chmod(0o700)
            script = root / "workflow.sh"
            script.write_text(step["run"].replace("/tmp/ledova-schema", str(root / "ledova-schema")))
            result = subprocess.run(
                [*commands[shell], str(script)],
                cwd=repository / "backend",
                env={
                    **os.environ,
                    "PATH": f"{root}{os.pathsep}{os.environ['PATH']}",
                    "PYTHONPATH": str(repository / "backend"),
                    "LEDOVA_SCHEMA_PIPELINE_VALID": "1" if valid else "0",
                },
                capture_output=True,
                text=True,
                timeout=20,
            )
            return (
                result,
                json.loads((root / "ledova-schema.json").read_text()),
                json.loads((root / "ledova-schema-environment.json").read_text()),
                (root / "ledova-schema-diagnostics.log").read_text(),
            )

    def test_ci_propagates_the_actual_export_refusal_after_tee_preserves_its_artifacts(self):
        result, document, report, diagnostics = self.invoke_ci_generation(valid=False)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(document["paths"], {})
        self.assertEqual(
            report["route_findings"], ["GET /api/synthetic/: registered operation is absent from the schema"]
        )
        self.assertIn("CommandError: Registered API operations differ from the schema", diagnostics)
        self.assertIn(diagnostics, result.stdout)

    def test_ci_retains_valid_generation_success_and_diagnostics(self):
        result, document, report, diagnostics = self.invoke_ci_generation(valid=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("/api/synthetic/", document["paths"])
        self.assertEqual(report["route_findings"], [])
        self.assertIn("Schema accounts for 1 registered operations", diagnostics)
        self.assertIn(diagnostics, result.stdout)
