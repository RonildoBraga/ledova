from dataclasses import dataclass
from math import isfinite

import requests

from authentication.security.v2_email import V2EmailError, normalize_v2_email
from authentication.services.v2_delivery_provider import V2DeliveryProviderResult

_SENDGRID_ENDPOINTS = frozenset(
    {
        "https://api.sendgrid.com/v3/mail/send",
        "https://api.eu.sendgrid.com/v3/mail/send",
    }
)
_MAX_TIMEOUT_SECONDS = 10


@dataclass(frozen=True, slots=True, repr=False)
class V2SendGridConfiguration:
    api_key: str
    api_url: str
    from_email: str
    timeout_seconds: float

    def __repr__(self) -> str:
        return "V2SendGridConfiguration(<redacted>)"

    def __str__(self) -> str:
        return "V2SendGridConfiguration(<redacted>)"


def _is_api_key(value: object) -> bool:
    return type(value) is str and 1 <= len(value) <= 512 and all(0x21 <= ord(character) <= 0x7E for character in value)


def _is_canonical_email(value: object) -> bool:
    if type(value) is not str:
        return False
    try:
        return normalize_v2_email(value) == value
    except V2EmailError:
        return False


def _is_timeout(value: object) -> bool:
    if type(value) is int:
        return 0 < value <= _MAX_TIMEOUT_SECONDS
    if type(value) is float:
        return isfinite(value) and 0 < value <= _MAX_TIMEOUT_SECONDS
    return False


def _is_configuration(configuration: object) -> bool:
    return (
        type(configuration) is V2SendGridConfiguration
        and _is_api_key(configuration.api_key)
        and type(configuration.api_url) is str
        and configuration.api_url in _SENDGRID_ENDPOINTS
        and _is_canonical_email(configuration.from_email)
        and _is_timeout(configuration.timeout_seconds)
    )


def _is_message(*, to_email: object, subject: object, html_content: object, text_content: object) -> bool:
    return (
        _is_canonical_email(to_email)
        and type(subject) is str
        and bool(subject.strip())
        and type(html_content) is str
        and bool(html_content.strip())
        and (text_content is None or type(text_content) is str)
    )


def send_v2_sendgrid_email(
    *,
    configuration: V2SendGridConfiguration,
    to_email: str,
    subject: str,
    html_content: str,
    text_content: str | None = None,
) -> V2DeliveryProviderResult:
    if not _is_configuration(configuration) or not _is_message(
        to_email=to_email,
        subject=subject,
        html_content=html_content,
        text_content=text_content,
    ):
        return V2DeliveryProviderResult.REJECTED

    content = [{"type": "text/html", "value": html_content}]
    if text_content is not None:
        content.insert(0, {"type": "text/plain", "value": text_content})
    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": configuration.from_email},
        "subject": subject,
        "content": content,
    }

    adapter = None
    try:
        request = requests.Request(
            method="POST",
            url=configuration.api_url,
            json=payload,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {configuration.api_key}",
            },
        )
        prepared_request = request.prepare()
        adapter = requests.adapters.HTTPAdapter(max_retries=0)
    except Exception:
        if adapter is not None:
            try:
                adapter.close()
            except Exception:
                pass
        return V2DeliveryProviderResult.REJECTED

    response = None
    try:
        response = adapter.send(
            prepared_request,
            timeout=(configuration.timeout_seconds, configuration.timeout_seconds),
            stream=True,
            verify=True,
            cert=None,
            proxies={},
        )
    except Exception:
        result = V2DeliveryProviderResult.AMBIGUOUS
    else:
        try:
            status_code = response.status_code
        except Exception:
            result = V2DeliveryProviderResult.AMBIGUOUS
        else:
            if type(status_code) is not int:
                result = V2DeliveryProviderResult.AMBIGUOUS
            elif status_code == 202:
                result = V2DeliveryProviderResult.ACCEPTED
            elif 400 <= status_code <= 499:
                result = V2DeliveryProviderResult.REJECTED
            else:
                result = V2DeliveryProviderResult.AMBIGUOUS
    finally:
        if response is not None:
            try:
                response.close()
            except Exception:
                pass
        try:
            adapter.close()
        except Exception:
            pass
    return result
