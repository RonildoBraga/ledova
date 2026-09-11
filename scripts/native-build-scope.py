import argparse
import json
import os
import re
import subprocess
from pathlib import Path

NATIVE_INPUT_PREFIXES = ("mobile/", "packages/shared/")
NATIVE_INPUT_FILES = frozenset(
    (
        "package.json",
        "package-lock.json",
        "npm-shrinkwrap.json",
        ".npmrc",
        "dashboard/package.json",
        ".gitattributes",
        ".github/workflows/mobile-native.yml",
        "scripts/native-build-scope.py",
        "scripts/tests/test_native_build_scope.py",
    )
)


def native_scope(event_name, payload, repository):
    if event_name not in ("pull_request", "push"):
        return {"required": True, "reason": "Unconditional native run"}
    try:
        if event_name == "pull_request":
            request = payload["pull_request"]
            base = request["base"]["sha"]
            head = request["head"]["sha"]
        else:
            base = payload["before"]
            head = payload["after"]
        if not all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value) for value in (base, head)):
            raise ValueError
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", base, head],
            cwd=repository,
            check=True,
            capture_output=True,
            timeout=30,
        )
        diff = subprocess.run(
            ["git", "diff", "--no-ext-diff", "--no-renames", "--name-only", "-z", base, head, "--"],
            cwd=repository,
            check=True,
            capture_output=True,
            timeout=30,
        ).stdout
        if diff and not diff.endswith(b"\0"):
            raise ValueError
        paths = diff[:-1].decode("utf-8").split("\0") if diff else []
        if any(not path or any(part in ("", ".", "..") for part in path.split("/")) for path in paths):
            raise ValueError
    except (KeyError, TypeError, ValueError, OSError, subprocess.SubprocessError):
        return {"required": True, "reason": "Complete ancestor comparison unavailable"}
    required = any(path.startswith(NATIVE_INPUT_PREFIXES) or path in NATIVE_INPUT_FILES for path in paths)
    return {
        "required": required,
        "reason": "Mobile or native build input changed" if required else "No mobile or native build inputs changed",
        "changed_files": len(paths),
    }


def native_verdict(needs):
    try:
        routing = needs["scope"]
        if routing["result"] != "success":
            return False
        required = routing["outputs"]["required"]
        if required not in ("true", "false"):
            return False
        expected = "success" if required == "true" else "skipped"
        return all(needs[platform]["result"] == expected for platform in ("android", "ios"))
    except (KeyError, TypeError):
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("route", "verdict"))
    parser.add_argument("--event", default=os.environ.get("GITHUB_EVENT_NAME"))
    parser.add_argument("--event-file", default=os.environ.get("GITHUB_EVENT_PATH"))
    parser.add_argument("--repository", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args()
    if args.command == "verdict":
        try:
            needs = json.loads(os.environ.get("NATIVE_JOB_RESULTS", "null"))
        except ValueError:
            needs = None
        passed = native_verdict(needs)
        print("Native CI requirements satisfied" if passed else "Native CI routing or required builds did not succeed")
        return 0 if passed else 1
    try:
        payload = json.loads(Path(args.event_file).read_text())
    except (TypeError, ValueError, OSError):
        payload = None
    decision = native_scope(args.event, payload, args.repository)
    print(json.dumps(decision))
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a") as stream:
            stream.write(f"required={str(decision['required']).lower()}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
