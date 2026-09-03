"""SendGrid transactional email client."""

import logging
from urllib.parse import urlsplit

import requests
from django.conf import settings
from django.core.mail import send_mail
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)

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
        self.api_key = settings.SENDGRID_API_KEY
        self.api_url = _configured_api_url(settings.SENDGRID_API_URL)
        self.from_email = settings.DEFAULT_FROM_EMAIL
        self.timeout = settings.SENDGRID_TIMEOUT

    def send_email(self, to_email, subject, html_content, from_email=None, text_content=None):
        sender = from_email or self.from_email
        if not self.api_key:
            # No SendGrid key: hand the message to Django's EMAIL_BACKEND (console in DEBUG).
            send_mail(subject, text_content or strip_tags(html_content), sender, [to_email], html_message=html_content)
            logger.info("Email sent through EMAIL_BACKEND (no SendGrid key)")
            return {"success": True, "message_id": ""}
        if not self.api_url:
            logger.error("SENDGRID_API_URL not configured or invalid")
            return {"success": False, "error": "SENDGRID_API_URL not configured or invalid"}

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
            logger.error("SendGrid request failed")
            return {"success": False, "error": "SendGrid request failed"}

        if response.status_code == 202:
            message_id = response.headers.get("X-Message-Id", "")
            logger.info("Email accepted by SendGrid")
            return {"success": True, "message_id": message_id}

        logger.error(f"SendGrid rejected request with HTTP {response.status_code}")
        return {"success": False, "error": f"SendGrid rejected request with HTTP {response.status_code}"}


sendgrid_client = SendGridClient()
