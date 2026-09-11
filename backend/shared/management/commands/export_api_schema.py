import json
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from django.db.migrations.executor import MigrationExecutor

from shared.api.routes import (
    PROVIDER_EXCLUSIONS,
    registered_routes,
    schema_route_drift,
    schema_routes,
)
from shared.api.schema_environment import environment_drift, measured_environment
from shared.db import current_alias


class Command(BaseCommand):
    help = "Generate OpenAPI using the recorded PostgreSQL toolchain and check registered operation coverage."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, type=Path)
        parser.add_argument("--report", required=True, type=Path)

    def handle(self, *args, **options):
        report = options["report"]
        report.parent.mkdir(parents=True, exist_ok=True)
        measured = measured_environment()
        findings = environment_drift(measured)
        measured["environment_findings"] = findings
        report.write_text(json.dumps(measured, indent=2, sort_keys=True) + "\n")
        if findings:
            raise CommandError("Schema generator environment differs:\n  " + "\n  ".join(findings))
        executor = MigrationExecutor(connections[current_alias()])
        if executor.migration_plan(executor.loader.graph.leaf_nodes()):
            raise CommandError("Apply all migrations to the isolated schema database before generation.")
        destination = options["file"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        call_command("spectacular", format="openapi-json", file=str(destination), fail_on_warn=True)
        document = json.loads(destination.read_text())
        registered = registered_routes()
        findings = schema_route_drift(document, registered)
        measured.update(
            registered_operations=sorted(registered),
            schema_operations=sorted(schema_routes(document)),
            provider_exclusions=sorted(PROVIDER_EXCLUSIONS),
            route_findings=findings,
        )
        report.write_text(json.dumps(measured, indent=2, sort_keys=True) + "\n")
        if findings:
            raise CommandError("Registered API operations differ from the schema:\n  " + "\n  ".join(findings))
        self.stdout.write(
            f"Schema accounts for {len(registered) - len(PROVIDER_EXCLUSIONS)} registered operations "
            f"and {len(PROVIDER_EXCLUSIONS)} deliberate provider exclusions."
        )
