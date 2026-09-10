import argparse
import json
import os
import re
import subprocess
from pathlib import Path


def native_scope(event_name, payload, repository):
    if event_name != "pull_request":
        return {"required": True, "reason": "Unconditional native run"}
    try:
        request = payload["pull_request"]
        base = request["base"]["sha"]
        head = request["head"]["sha"]
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
        if not diff or not diff.endswith(b"\0"):
            raise ValueError
        paths = diff[:-1].decode("utf-8").split("\0")
        if any(not path or any(part in ("", ".", "..") for part in path.split("/")) for path in paths):
            raise ValueError
    except (KeyError, TypeError, ValueError, OSError, subprocess.SubprocessError):
        return {"required": True, "reason": "Complete current-base comparison unavailable"}
    required = any(not path.startswith(("backend/", "docs/")) for path in paths)
    return {
        "required": required,
        "reason": "Native or unclassified input changed" if required else "Only backend and documentation changed",
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
