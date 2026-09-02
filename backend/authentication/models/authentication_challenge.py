import uuid

from django.conf import settings
from django.db import models
from django.db.models.functions import Length
from django.db.models.lookups import Exact

from authentication.security.v2_email import (
    V2EmailDestinationKey,
    V2EmailIsPrintableASCII,
)


class AuthenticationChallenge(models.Model):
    class Purpose(models.TextChoices):
        SIGNUP = "signup", "Signup"
        EMAIL_CHANGE = "email_change", "Email change"
        PASSWORD_RESET = "password_reset", "Password reset"

    class Transport(models.TextChoices):
        BROWSER = "browser", "Browser"
        NATIVE = "native", "Native"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CONSUMED = "consumed", "Consumed"
        EXHAUSTED = "exhausted", "Exhausted"
        EXPIRED = "expired", "Expired"
        SUPERSEDED = "superseded", "Superseded"
        INVALIDATED = "invalidated", "Invalidated"

    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="authentication_challenges",
        editable=False,
    )
    purpose = models.CharField(max_length=16, choices=Purpose.choices, editable=False)
    transport = models.CharField(max_length=8, choices=Transport.choices, editable=False)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN, editable=False)
    pending_context_key_id = models.CharField(max_length=64, null=True, blank=True, editable=False)
    pending_context_digest = models.BinaryField(max_length=32, null=True, blank=True, editable=False)
    target_email = models.EmailField(max_length=254, null=True, blank=True, editable=False)
    otp_failure_count = models.PositiveSmallIntegerField(default=0, editable=False)
    created_at = models.DateTimeField(editable=False)
    expires_at = models.DateTimeField(editable=False)
    resolved_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        db_table = "authentication_challenge"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["user", "purpose", "status", "expires_at"],
                name="auth_chal_user_state_idx",
            ),
            models.Index(fields=["status", "expires_at"], name="auth_chal_expiry_idx"),
            models.Index(
                fields=["pending_context_key_id", "status", "created_at"],
                name="auth_chal_ctx_key_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(purpose__in=["signup", "email_change", "password_reset"]),
                name="auth_chal_purpose_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(transport__in=["browser", "native"]),
                name="auth_chal_transport_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    status__in=["open", "consumed", "exhausted", "expired", "superseded", "invalidated"]
                ),
                name="auth_chal_status_valid",
            ),
            models.CheckConstraint(
                condition=(
                    (
                        models.Q(
                            purpose__in=["signup", "email_change"],
                            pending_context_digest__isnull=False,
                            pending_context_key_id__isnull=False,
                        )
                        & ~models.Q(pending_context_key_id="")
                    )
                    | models.Q(
                        purpose="password_reset",
                        pending_context_digest__isnull=True,
                        pending_context_key_id__isnull=True,
                    )
                ),
                name="auth_chal_context_state",
            ),
            models.CheckConstraint(
                condition=models.Q(pending_context_digest__isnull=True) | Exact(Length("pending_context_digest"), 32),
                name="auth_chal_context_len",
            ),
            models.CheckConstraint(
                condition=models.Q(pending_context_key_id__isnull=True)
                | models.Q(pending_context_key_id__regex=r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z"),
                name="auth_chal_context_key",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        purpose="email_change",
                        status="open",
                        target_email__isnull=False,
                    )
                    | (~models.Q(purpose="email_change", status="open") & models.Q(target_email__isnull=True))
                ),
                name="auth_chal_target_state",
            ),
            models.CheckConstraint(
                condition=models.Q(target_email__isnull=True) | V2EmailIsPrintableASCII(models.F("target_email")),
                name="auth_chal_target_ascii",
            ),
            models.CheckConstraint(
                condition=models.Q(target_email__isnull=True)
                | models.Q(target_email=V2EmailDestinationKey(models.F("target_email"))),
                name="auth_chal_target_canon",
            ),
            models.CheckConstraint(
                condition=models.Q(otp_failure_count__gte=0, otp_failure_count__lte=5),
                name="auth_chal_failure_range",
            ),
            models.CheckConstraint(
                condition=~models.Q(purpose="password_reset") | models.Q(otp_failure_count=0),
                name="auth_chal_reset_no_failures",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        status="exhausted",
                        purpose__in=["signup", "email_change"],
                        otp_failure_count=5,
                    )
                    | (~models.Q(status="exhausted") & models.Q(otp_failure_count__lt=5))
                ),
                name="auth_chal_exhausted_state",
            ),
            models.CheckConstraint(
                condition=~models.Q(status="superseded") | models.Q(purpose="email_change"),
                name="auth_chal_supersede_purpose",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status="open", resolved_at__isnull=True)
                    | (~models.Q(status="open") & models.Q(resolved_at__isnull=False))
                ),
                name="auth_chal_resolved_state",
            ),
            models.CheckConstraint(
                condition=models.Q(expires_at__gt=models.F("created_at")),
                name="auth_chal_expiry_order",
            ),
            models.CheckConstraint(
                condition=models.Q(resolved_at__isnull=True) | models.Q(resolved_at__gte=models.F("created_at")),
                name="auth_chal_resolved_order",
            ),
            models.UniqueConstraint(
                fields=["user", "purpose"],
                condition=models.Q(status="open"),
                name="auth_chal_open_user_uniq",
            ),
        ]

    def __str__(self):
        return "AuthenticationChallenge(<redacted>)"

    def __repr__(self):
        return "AuthenticationChallenge(<redacted>)"
