import logging
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version

AUDITED_PROCRASTINATE_VERSION = "3.9.0"
V2_DELIVERY_TASK_NAME = "authentication.deliver_v2_challenge"

_MISSING = object()
_VERSION_ERROR = "Unsupported Procrastinate logging contract."


def _v2_job_match(value):
    if type(value) is not dict:
        return None
    task_name = value.get("task_name")
    if type(task_name) is not str:
        return None
    return task_name == V2_DELIVERY_TASK_NAME


class V2ProcrastinateLogFilter(logging.Filter):
    def __init__(self):
        super().__init__()
        try:
            installed_version = package_version("procrastinate")
        except PackageNotFoundError:
            raise RuntimeError(_VERSION_ERROR) from None
        if installed_version != AUDITED_PROCRASTINATE_VERSION:
            raise RuntimeError(_VERSION_ERROR)

    def filter(self, record):
        if record.name != "procrastinate" and not record.name.startswith("procrastinate."):
            return True
        if record.__dict__.get("action") == "ending_job":
            return False

        job = record.__dict__.get("job", _MISSING)
        if job is not _MISSING and _v2_job_match(job) is not False:
            return False

        jobs = record.__dict__.get("jobs", _MISSING)
        if jobs is _MISSING:
            return True
        if type(jobs) is not list:
            return False
        return all(_v2_job_match(item) is False for item in jobs)
