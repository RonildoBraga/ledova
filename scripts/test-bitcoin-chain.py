"""Run the wallet submission pipeline against an isolated, version-pinned Bitcoin regtest node."""

import argparse
import base64
import hashlib
import json
import os
import platform
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path
from urllib.request import Request, urlopen

VERSION = "31.1"
ARCHIVE_HASH = "b80d9c3e04da78fb6f0569685673418cf686fadba9042d926d13fb87ff503f9e"
URL = f"https://bitcoincore.org/bin/bitcoin-core-{VERSION}/bitcoin-{VERSION}-x86_64-linux-gnu.tar.gz"


def rpc(url, cookie, method):
    authorization = base64.b64encode(cookie.read_bytes().strip()).decode()
    request = Request(
        url,
        data=json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": method, "params": []}
        ).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Basic {authorization}",
        },
    )
    with urlopen(request, timeout=3) as response:
        result = json.load(response)
    if result.get("error"):
        raise RuntimeError(f"Bitcoin readiness RPC failed for {method}")
    return result["result"]


def bitcoin_binary(directory):
    configured = os.environ.get("BITCOIN_TEST_BINARY")
    if configured:
        binary = Path(configured).resolve(strict=True)
    else:
        if platform.system() != "Linux" or platform.machine() != "x86_64":
            raise RuntimeError(
                "Set BITCOIN_TEST_BINARY to an installed Bitcoin Core 31.1 binary on this platform."
            )
        archive = directory / "bitcoin.tar.gz"
        with urlopen(URL, timeout=60) as source, archive.open("wb") as target:
            while chunk := source.read(1024 * 1024):
                target.write(chunk)
        with archive.open("rb") as source:
            checksum = hashlib.file_digest(source, "sha256").hexdigest()
        if checksum != ARCHIVE_HASH:
            raise RuntimeError(
                "The Bitcoin Core release archive does not match its pinned SHA256."
            )
        with tarfile.open(archive) as release:
            with release.extractfile(f"bitcoin-{VERSION}/bin/bitcoind") as source:
                binary = directory / "bitcoind"
                binary.write_bytes(source.read())
        binary.chmod(0o700)
    version = subprocess.check_output(
        [str(binary), "-version"], text=True
    ).splitlines()[0]
    if version != "Bitcoin Core daemon version v31.1.0 bitcoind":
        raise RuntimeError(f"Expected Bitcoin Core 31.1.0, got {version}")
    print(version, flush=True)
    return binary


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=18579)
    parser.add_argument("--settings", default="ledova_backend.settings.test_postgres")
    arguments = parser.parse_args()
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", arguments.port))
    root = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory(prefix="ledova-bitcoin-regtest-") as name:
        directory = Path(name)
        binary = bitcoin_binary(directory)
        data = directory / "data"
        data.mkdir()
        cookie = data / "regtest" / ".cookie"
        url = f"http://127.0.0.1:{arguments.port}"
        with (directory / "node.log").open("w+") as log:
            process = subprocess.Popen(
                [
                    str(binary),
                    f"-datadir={data}",
                    "-regtest=1",
                    "-server=1",
                    f"-rpcport={arguments.port}",
                    "-rpcbind=127.0.0.1",
                    "-rpcallowip=127.0.0.1",
                    "-networkactive=0",
                    "-listen=0",
                    "-dnsseed=0",
                    "-connect=0",
                    "-txindex=1",
                    "-fallbackfee=0.0001",
                    "-printtoconsole=1",
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            try:
                deadline = time.monotonic() + 30
                while True:
                    if process.poll() is not None:
                        raise RuntimeError(
                            "The isolated Bitcoin node exited before readiness."
                        )
                    try:
                        chain = rpc(url, cookie, "getblockchaininfo")
                        network = rpc(url, cookie, "getnetworkinfo")
                        break
                    except (OSError, ValueError, RuntimeError):
                        if time.monotonic() >= deadline:
                            raise RuntimeError(
                                "The isolated Bitcoin node did not become ready."
                            ) from None
                        time.sleep(0.1)
                if (
                    chain["chain"] != "regtest"
                    or network["networkactive"]
                    or network["connections"]
                ):
                    raise RuntimeError(
                        "Bitcoin chain tests require an isolated regtest node with external networking off."
                    )
                print(
                    "Isolated regtest: external networking disabled, zero peers",
                    flush=True,
                )
                environment = {
                    **os.environ,
                    "BITCOIN_TEST_RPC_URL": url,
                    "BITCOIN_TEST_COOKIE": str(cookie),
                    "BITCOIN_NETWORK": "regtest",
                    "SECRET_KEY": "bitcoin-regtest-synthetic-only",
                    "STORAGE_BACKEND": "local",
                }
                return subprocess.run(
                    [
                        sys.executable,
                        "manage.py",
                        "test",
                        "wallets.tests.test_bitcoin_submission_chain",
                        f"--settings={arguments.settings}",
                        "--noinput",
                    ],
                    cwd=root / "backend",
                    env=environment,
                    check=False,
                ).returncode
            except Exception:
                log.seek(0)
                print("\n".join(log.read().splitlines()[-60:]), file=sys.stderr)
                raise
            finally:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(run())
