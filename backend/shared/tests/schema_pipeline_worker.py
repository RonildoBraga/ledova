import argparse
import json
import os
from pathlib import Path
from unittest.mock import patch

import django


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("launcher", choices=["manage.py"])
    parser.add_argument("command", choices=["migrate", "export_api_schema"])
    parser.add_argument("--settings", required=True)
    parser.add_argument("--noinput", action="store_true")
    parser.add_argument("--file", type=Path)
    parser.add_argument("--report", type=Path)
    arguments = parser.parse_args()
    if arguments.command == "migrate":
        print("Synthetic migration prerequisite already applied.")
        return
    os.environ["DJANGO_SETTINGS_MODULE"] = "ledova_backend.settings.test"
    django.setup()
    from django.core.management import execute_from_command_line

    from shared.api.routes import PROVIDER_EXCLUSIONS
    from shared.api.schema_environment import expected_environment

    expected = expected_environment()
    measured = {
        "python": expected["python"],
        "settings": expected["settings"],
        "packages": expected["packages"],
        "database_vendor": "postgresql",
        "postgresql_version": expected["postgresql_major"] * 10000 + 4,
    }
    paths = {}
    if os.environ["LEDOVA_SCHEMA_PIPELINE_VALID"] == "1":
        paths["/api/synthetic/"] = {"get": {"responses": {"204": {"description": "Empty"}}}}

    def generate(*args, **kwargs):
        arguments.file.write_text(json.dumps({"openapi": "3.0.3", "paths": paths}))

    command = "shared.management.commands.export_api_schema."
    with (
        patch(command + "measured_environment", return_value=measured),
        patch(command + "MigrationExecutor") as executor,
        patch(command + "call_command", side_effect=generate),
        patch(command + "registered_routes", return_value=PROVIDER_EXCLUSIONS | {("get", "/api/synthetic/")}),
    ):
        executor.return_value.migration_plan.return_value = []
        execute_from_command_line(
            [
                arguments.launcher,
                arguments.command,
                "--file",
                str(arguments.file),
                "--report",
                str(arguments.report),
            ]
        )


if __name__ == "__main__":
    main()
