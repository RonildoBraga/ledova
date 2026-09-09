import json
import sys
from dataclasses import asdict

from integrations.abr.client import (
    MAX_WORKER_BYTES,
    RegistryObservation,
    request_company,
)


def main():
    try:
        request = json.loads(sys.stdin.buffer.read(MAX_WORKER_BYTES))
        observation = request_company(**request)
    except (TypeError, ValueError):
        observation = RegistryObservation(reason="invalid_response")
    output = json.dumps(asdict(observation), default=lambda value: value.isoformat()).encode()
    sys.stdout.buffer.write(output)


if __name__ == "__main__":
    main()
