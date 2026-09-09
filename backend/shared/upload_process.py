import os
import subprocess
import sys
import tempfile
from pathlib import Path

from shared.upload_errors import UploadUnavailable


class UploadProcessTimeout(Exception):
    pass


def run_upload_worker(worker, arguments, raw, seconds, output_limit):
    with tempfile.TemporaryDirectory(prefix="ledova-upload-") as directory:
        output = Path(directory) / "result"
        try:
            with output.open("wb") as destination:
                result = subprocess.run(
                    [sys.executable, "-I", "-B", str(worker), *arguments],
                    input=raw,
                    stdout=destination,
                    stderr=subprocess.DEVNULL,
                    cwd=directory,
                    env={"PATH": os.defpath, "LANG": "C.UTF-8"},
                    timeout=seconds,
                    check=False,
                )
            with output.open("rb") as stream:
                return result.returncode, stream.read(output_limit + 1)
        except subprocess.TimeoutExpired:
            raise UploadProcessTimeout() from None
        except OSError:
            raise UploadUnavailable() from None
