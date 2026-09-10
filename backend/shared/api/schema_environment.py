import json
import platform
from importlib.metadata import version
from pathlib import Path

from django.conf import settings
from django.db import connections

from shared.db import current_alias

SCHEMA_DIRECTORY = Path(__file__).resolve().parents[2] / "schema"


def expected_environment():
    expected = json.loads((SCHEMA_DIRECTORY / "environment.json").read_text())
    expected["packages"] = dict(
        line.split("==") for line in (SCHEMA_DIRECTORY / "requirements.txt").read_text().splitlines() if line
    )
    return expected


def measured_environment():
    expected = expected_environment()
    connection = connections[current_alias()]
    return {
        "python": platform.python_version(),
        "settings": settings.SETTINGS_MODULE,
        "packages": {name: version(name) for name in expected["packages"]},
        "database_vendor": connection.vendor,
        "postgresql_version": (connection.pg_version if connection.vendor == "postgresql" else None),
    }


def environment_drift(measured):
    expected = expected_environment()
    findings = []
    for name in ("python", "settings"):
        if measured.get(name) != expected[name]:
            findings.append(f"{name}: expected {expected[name]}, found {measured.get(name)}")
    for name, required in expected["packages"].items():
        actual = measured.get("packages", {}).get(name)
        if actual != required:
            findings.append(f"{name}: expected {required}, found {actual}")
    if measured.get("database_vendor") != "postgresql":
        findings.append("Schema generation requires PostgreSQL; SQLite changes numeric bounds and formats")
    elif (measured.get("postgresql_version") or 0) // 10000 != expected["postgresql_major"]:
        findings.append(
            f"Expected PostgreSQL {expected['postgresql_major']}, found {measured.get('postgresql_version')}"
        )
    return findings
