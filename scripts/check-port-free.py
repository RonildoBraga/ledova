#!/usr/bin/env python3
"""Fail with a legible message when a TCP port is already taken."""

from __future__ import annotations

import argparse
import socket
import sys


def is_free(host: str, port: int) -> tuple[bool, str]:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, port))
        except OSError as error:
            return False, error.strerror or str(error)
    return True, ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("port", type=int)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--variable", default="CHAIN_TEST_PORT")
    args = parser.parse_args(argv)

    free, reason = is_free(args.host, args.port)
    if free:
        return 0

    print(
        f"{args.variable}={args.port} is already in use on {args.host} ({reason}). "
        f"Another Hardhat node, another worktree or another service is listening there. "
        f"Stop it, or pick a free port: make chain-test {args.variable}=<port>.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
