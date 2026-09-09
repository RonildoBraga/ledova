import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from threading import Event, Timer
from time import monotonic
from xml.etree import ElementTree

import requests
from django.conf import settings
from django.utils.dateparse import parse_date, parse_datetime

ABR_SERVICE = "https://abr.business.gov.au/abrxmlsearch/abrxmlsearch.asmx"
ABR_NAMESPACE = "http://abr.business.gov.au/ABRXMLSearch/"
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_WORKER_BYTES = 4096
LOOKUP_DEADLINE_SECONDS = 15
WORKER_COMMAND = (sys.executable, "-m", "integrations.abr.worker")


@dataclass(frozen=True)
class RegistryObservation:
    reason: str = ""
    abn: str = ""
    acn: str = ""
    entity_name: str = ""
    entity_type: str = ""
    entity_status: str = ""
    effective_from: date | None = None
    retrieved_at: str = ""
    register_updated_at: date | None = None


def _text(element, path):
    qualified = "/".join(f"{{{ABR_NAMESPACE}}}{part}" for part in path.split("/"))
    matches = element.findall(qualified)
    if len(matches) > 1:
        raise ValueError("Ambiguous registry response")
    return (matches[0].text or "").strip() if matches else ""


def parse_observation(content):
    if len(content) > MAX_RESPONSE_BYTES:
        return RegistryObservation(reason="invalid_response")
    try:
        root = ElementTree.fromstring(content)
        response = root.find(f"{{{ABR_NAMESPACE}}}response")
        if response is None:
            return RegistryObservation(reason="invalid_response")
        exception = response.find(f"{{{ABR_NAMESPACE}}}exception")
        if exception is not None:
            description = _text(exception, "exceptionDescription").casefold()
            not_found = _text(exception, "exceptionCode") == "SEARCH" and description == "no records found"
            return RegistryObservation(reason="not_found" if not_found else "provider_error")
        entities = [element for element in response if element.tag.rsplit("}", 1)[-1].startswith("businessEntity")]
        if len(entities) != 1:
            return RegistryObservation(reason="invalid_response")
        entity = entities[0]
        observation = RegistryObservation(
            abn=_text(entity, "ABN/identifierValue"),
            acn=_text(entity, "ASICNumber"),
            entity_name=_text(entity, "mainName/organisationName"),
            entity_type=_text(entity, "entityType/entityTypeCode"),
            entity_status=_text(entity, "entityStatus/entityStatusCode"),
            effective_from=parse_date(_text(entity, "entityStatus/effectiveFrom")),
            retrieved_at=_text(response, "dateTimeRetrieved"),
            register_updated_at=parse_date(_text(response, "dateRegisterLastUpdated")),
        )
        for value, limit in (
            (observation.entity_name, 255),
            (observation.entity_type, 16),
            (observation.entity_status, 32),
            (observation.retrieved_at, 40),
        ):
            if len(value) > limit:
                return RegistryObservation(reason="invalid_response")
        if (observation.abn and not re.fullmatch(r"[0-9]{11}", observation.abn)) or (
            observation.acn and not re.fullmatch(r"[0-9]{9}", observation.acn)
        ):
            return RegistryObservation(reason="invalid_response")
        if observation.retrieved_at and parse_datetime(observation.retrieved_at) is None:
            return RegistryObservation(reason="invalid_response")
        if _text(entity, "ABN/isCurrentIndicator") not in ("", "Y"):
            return RegistryObservation(reason="invalid_response")
        return observation
    except (ElementTree.ParseError, ValueError, TypeError, LookupError):
        return RegistryObservation(reason="invalid_response")


def request_company(*, acn, abn, guid):
    method = "SearchByABNv202001" if abn else "SearchByASICv201408"
    try:
        with requests.post(
            f"{ABR_SERVICE}/{method}",
            data={"searchString": abn or acn, "includeHistoricalDetails": "N", "authenticationGuid": guid},
            timeout=(3, 10),
            allow_redirects=False,
            stream=True,
            headers={"Accept-Encoding": "identity"},
        ) as response:
            if response.status_code != 200:
                return RegistryObservation(reason="provider_error")
            length = response.headers.get("Content-Length")
            if length is not None and (not length.isdecimal() or int(length) > MAX_RESPONSE_BYTES):
                return RegistryObservation(reason="invalid_response")
            if response.headers.get("Content-Encoding", "identity").casefold() != "identity":
                return RegistryObservation(reason="invalid_response")
            content = bytearray()
            for chunk in response.iter_content(chunk_size=65536):
                if len(content) + len(chunk) > MAX_RESPONSE_BYTES:
                    return RegistryObservation(reason="invalid_response")
                content.extend(chunk)
            return parse_observation(bytes(content))
    except requests.Timeout:
        return RegistryObservation(reason="timeout")
    except requests.RequestException:
        return RegistryObservation(reason="unavailable")


def _expire_worker(process, expired):
    expired.set()
    process.kill()


def _worker_observation(output):
    try:
        fields = json.loads(output)
        for field in ("effective_from", "register_updated_at"):
            if fields.get(field) is not None:
                fields[field] = parse_date(fields[field])
        return RegistryObservation(**fields)
    except (ValueError, TypeError, AttributeError):
        return RegistryObservation(reason="invalid_response")


def lookup_company(*, acn, abn):
    guid = settings.ABR_AUTH_GUID
    if not guid:
        return RegistryObservation(reason="unconfigured")
    request = json.dumps({"acn": acn, "abn": abn, "guid": guid}).encode()
    if len(request) > MAX_WORKER_BYTES:
        return RegistryObservation(reason="invalid_configuration")
    deadline = monotonic() + LOOKUP_DEADLINE_SECONDS
    try:
        with subprocess.Popen(
            WORKER_COMMAND,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=Path(__file__).resolve().parents[2],
            env={"PYTHONDONTWRITEBYTECODE": "1"},
            close_fds=True,
        ) as process:
            expired = Event()
            timer = Timer(max(0, deadline - monotonic()), _expire_worker, args=(process, expired))
            timer.daemon = True
            try:
                timer.start()
            except RuntimeError:
                process.kill()
                process.wait()
                return RegistryObservation(reason="unavailable")
            output = b""
            failed = False
            try:
                process.stdin.write(request)
                process.stdin.close()
                output = process.stdout.read(MAX_WORKER_BYTES + 1)
                if len(output) > MAX_WORKER_BYTES:
                    process.kill()
                process.wait()
            except OSError:
                failed = True
            finally:
                timer.cancel()
                timer.join()
                if process.poll() is None:
                    process.kill()
                process.wait()
            if expired.is_set() or monotonic() >= deadline:
                return RegistryObservation(reason="timeout")
            if len(output) > MAX_WORKER_BYTES:
                return RegistryObservation(reason="invalid_response")
            if failed or process.returncode:
                return RegistryObservation(reason="unavailable")
    except OSError:
        return RegistryObservation(reason="unavailable")
    return _worker_observation(output)
