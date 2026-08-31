"""SendGrid transactional email client."""

import logging
from urllib.parse import urlsplit

import requests
from django.conf import settings

from shared.utils.logging_utils import LoggingContext

logger = logging.getLogger("ledova_backend")

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "host.docker.internal"})


def _configured_api_url(value: str) -> str:
    candidate = value.strip()
    parsed = urlsplit(candidate)
    is_local_http = parsed.scheme == "http" and parsed.hostname in _LOCAL_HOSTS

    if (
        not candidate
        or (parsed.scheme != "https" and not is_local_http)
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        return ""
    return candidate


class SendGridClient:
    def __init__(self):
        self.api_key = getattr(settings, "SENDGRID_API_KEY", "")
        self.api_url = _configured_api_url(getattr(settings, "SENDGRID_API_URL", ""))
        self.from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@localhost")
        self.timeout = int(getattr(settings, "SENDGRID_TIMEOUT", 10))

    def send_email(self, to_email, subject, html_content, from_email=None, text_content=None):
        if not self.api_key:
            logger.error(f"{LoggingContext.INTEGRATIONS} SENDGRID_API_KEY not configured")
            return {"success": False, "error": "SENDGRID_API_KEY not configured"}
        if not self.api_url:
            logger.error(f"{LoggingContext.INTEGRATIONS} SENDGRID_API_URL not configured or invalid")
            return {"success": False, "error": "SENDGRID_API_URL not configured or invalid"}

        sender = from_email or self.from_email
        content = [{"type": "text/html", "value": html_content}]
        if text_content:
            content.insert(0, {"type": "text/plain", "value": text_content})

        payload = {
            "personalizations": [{"to": [{"email": to_email}]}],
            "from": {"email": sender},
            "subject": subject,
            "content": content,
        }

        try:
            response = requests.post(
                self.api_url,
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout,
            )
        except requests.RequestException:
            logger.error(f"{LoggingContext.INTEGRATIONS} SendGrid request failed")
            return {"success": False, "error": "SendGrid request failed"}

        if response.status_code == 202:
            message_id = response.headers.get("X-Message-Id", "")
            logger.info(f"{LoggingContext.INTEGRATIONS} Email accepted by SendGrid")
            return {"success": True, "message_id": message_id}

        logger.error(f"{LoggingContext.INTEGRATIONS} SendGrid rejected request with HTTP {response.status_code}")
        return {"success": False, "error": f"SendGrid rejected request with HTTP {response.status_code}"}


sendgrid_client = SendGridClient()
