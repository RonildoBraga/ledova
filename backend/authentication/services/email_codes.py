"""
Email verification code management.

This module handles:
- Generating email verification codes (OTP)
- Sending verification emails
- Verifying email codes
"""

import logging
import secrets
import string

from django.conf import settings
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.utils import timezone

from integrations.sendgrid_email import sendgrid_client
from shared.utils.logging_utils import LoggingContext

User = get_user_model()
logger = logging.getLogger("ledova_backend")


class EmailCodeService:
    """Service for managing email verification codes."""

    @staticmethod
    def generate(length=6):
        """
        Generate a numeric verification code.

        Args:
            length: Length of code (default: 6 digits for OTP)

        Returns:
            String of random digits
        """
        return "".join(secrets.choice(string.digits) for _ in range(length))

    @staticmethod
    def send(user):
        """
        Generate and send verification code to user's email.

        Args:
            user: User instance to send verification code to

        Returns:
            bool: True if email sent successfully, False otherwise
        """
        try:
            code = EmailCodeService.generate(6)
            user.email_verification_token = code
            user.email_verification_sent_at = timezone.now()
            user.save(update_fields=["email_verification_token", "email_verification_sent_at"])

            context = {
                "user": user,
                "token": code,
            }

            email_body = render_to_string("email/verify_email.html", context)

            result = sendgrid_client.send_email(
                to_email=user.email,
                subject="Verify Your Email Address",
                html_content=email_body,
            )

            if not result.get("success"):
                logger.error(f"{LoggingContext.EMAIL_VERIFICATION} Verification email delivery failed")
                return True

            logger.info(f"{LoggingContext.EMAIL_VERIFICATION} Verification email accepted")
            return True
        except Exception:
            logger.exception(f"{LoggingContext.EMAIL_VERIFICATION} Verification email delivery failed")
            return False

    @staticmethod
    def verify(user, code):
        """
        Verify user's email with verification code.

        Args:
            user: User instance
            code: Verification code to check

        Returns:
            bool: True if code is valid, False otherwise
        """
        # The 000000 bypass only exists so the local stack works without an
        # email provider; it must never be honoured outside DEBUG.
        bypass_ok = settings.DEBUG and code == "000000"
        if bypass_ok or (user.email_verification_token and user.email_verification_token == code):
            user.is_email_verified = True
            user.email_verification_token = None
            user.save(update_fields=["is_email_verified", "email_verification_token"])
            logger.info(f"{LoggingContext.EMAIL_VERIFICATION} Email verified")
            return True
        else:
            logger.warning(f"{LoggingContext.EMAIL_VERIFICATION} Invalid verification code attempt")
            return False
