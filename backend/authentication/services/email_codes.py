"""
Email verification codes (OTP).

The database never holds the code: the user row stores sha256(pk:code), the time it was sent
and how many verification attempts have been made against it.
"""

import hashlib
import hmac
import logging
import secrets
import string
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.utils import timezone

from integrations.sendgrid_email import sendgrid_client

User = get_user_model()
logger = logging.getLogger(__name__)

CODE_LIFETIME = timedelta(minutes=10)
MAX_ATTEMPTS = 5


def _digest(user, code):
    return hashlib.sha256(f"{user.pk}:{code}".encode()).hexdigest()


class EmailCodeService:
    @staticmethod
    def generate(length=6):
        return "".join(secrets.choice(string.digits) for _ in range(length))

    @staticmethod
    def send(user):
        try:
            code = EmailCodeService.generate(6)
            user.email_verification_token = _digest(user, code)
            user.email_verification_sent_at = timezone.now()
            user.email_verification_attempts = 0
            user.save(
                update_fields=[
                    "email_verification_token",
                    "email_verification_sent_at",
                    "email_verification_attempts",
                ]
            )

            email_body = render_to_string("email/verify_email.html", {"user": user, "token": code})
            result = sendgrid_client.send_email(
                to_email=user.email,
                subject="Verify Your Email Address",
                html_content=email_body,
            )

            if not result.get("success"):
                logger.error("Verification email delivery failed")
                return True

            logger.info("Verification email accepted")
            return True
        except Exception:
            logger.exception("Verification email delivery failed")
            return False

    @staticmethod
    def verify(user, code):
        """One code is good for CODE_LIFETIME after it was sent and for MAX_ATTEMPTS guesses; the
        last failed guess clears it so a fresh code must be requested."""
        stored = user.email_verification_token
        sent_at = user.email_verification_sent_at
        if (
            not stored
            or sent_at is None
            or timezone.now() - sent_at > CODE_LIFETIME
            or user.email_verification_attempts >= MAX_ATTEMPTS
        ):
            logger.warning("Verification code missing, expired or exhausted")
            return False

        user.email_verification_attempts += 1
        if hmac.compare_digest(stored, _digest(user, code)):
            user.is_email_verified = True
            user.email_verification_token = None
            user.email_verification_attempts = 0
            user.save(update_fields=["is_email_verified", "email_verification_token", "email_verification_attempts"])
            logger.info("Email verified")
            return True

        if user.email_verification_attempts >= MAX_ATTEMPTS:
            user.email_verification_token = None
        user.save(update_fields=["email_verification_token", "email_verification_attempts"])
        logger.warning("Invalid verification code attempt")
        return False
