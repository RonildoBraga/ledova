#!/usr/bin/env python3
"""Create and validate owner-only local development environment files."""

from __future__ import annotations

import argparse
import os
import secrets
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = {
    REPO_ROOT / "backend" / ".env": REPO_ROOT / "backend" / ".env.example",
    REPO_ROOT / "dashboard" / ".env": REPO_ROOT / "dashboard" / ".env.example",
    REPO_ROOT / "marketing" / ".env": REPO_ROOT / "marketing" / ".env.example",
    REPO_ROOT / "mobile" / ".env": REPO_ROOT / "mobile" / ".env.example",
}


def _create_exclusive(path: Path, content: str) -> None:
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        output.write(content)


def _read_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def initialize() -> None:
    for destination, template in TEMPLATES.items():
        content = template.read_text(encoding="utf-8")
        if destination.parent.name == "backend":
            content = content.replace("SECRET_KEY=\n", f"SECRET_KEY={secrets.token_urlsafe(48)}\n", 1)
            content = content.replace(
                "POSTGRES_PASSWORD=\n",
                f"POSTGRES_PASSWORD={secrets.token_urlsafe(32)}\n",
                1,
            )
        _create_exclusive(destination, content)


def validate() -> None:
    missing = [path for path in TEMPLATES if not path.is_file()]
    if missing:
        raise SystemExit("LOCAL_ENV_INCOMPLETE: run `make init-local`")

    backend_values = _read_values(REPO_ROOT / "backend" / ".env")
    invalid = [name for name in ("SECRET_KEY", "POSTGRES_PASSWORD") if not backend_values.get(name)]
    if invalid:
        raise SystemExit("LOCAL_ENV_INCOMPLETE: required backend values are blank")

    for path in TEMPLATES:
        path.chmod(0o600)
    print("LOCAL_ENV_READY")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="validate without creating files")
    args = parser.parse_args()
    if not args.check:
        initialize()
    validate()


if __name__ == "__main__":
    main()
