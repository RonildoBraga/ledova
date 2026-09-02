from django.conf import settings
from django.db import models
from django.utils import timezone

from shared.models import BaseModel


class AuthSession(BaseModel):
    class ClientType(models.TextChoices):
        BROWSER = "browser", "Browser"
        NATIVE = "native", "Native"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        REFRESH_CONFIRMATION_REQUIRED = (
            "refresh_confirmation_required",
            "Refresh confirmation required",
        )
        REVOKED = "revoked", "Revoked"

    class RevokeReason(models.TextChoices):
        SIGNED_OUT = "signed_out", "Signed out"
        SIGNED_OUT_ALL = "signed_out_all", "Signed out everywhere"
        PASSWORD_CHANGE = "password_change", "Password changed"
        PASSWORD_RESET = "password_reset", "Password reset"
        EMAIL_CHANGE = "email_change", "Email changed"
        ACCOUNT_DISABLED = "account_disabled", "Account disabled"
        ACCOUNT_DELETED = "account_deleted", "Account deleted"
        REFRESH_REUSED = "refresh_reused", "Refresh reused"
        CONFIRMATION_FAILED = "confirmation_failed", "Confirmation failed"
        ADMIN_REVOKED = "admin_revoked", "Administrator revoked"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="auth_sessions",
    )
    client_type = models.CharField(max_length=16, choices=ClientType.choices)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.ACTIVE)
    device_label = models.CharField(max_length=80, blank=True, default="")
    absolute_expires_at = models.DateTimeField()
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoke_reason = models.CharField(
        max_length=32,
        choices=RevokeReason.choices,
        blank=True,
        default="",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status", "-created_at"], name="auth_sess_user_state_idx"),
            models.Index(fields=["status", "absolute_expires_at"], name="auth_sess_expiry_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(client_type__in=["browser", "native"]),
                name="auth_session_client_type_valid",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(revoke_reason="")
                    | models.Q(
                        revoke_reason__in=[
                            "signed_out",
                            "signed_out_all",
                            "password_change",
                            "password_reset",
                            "email_change",
                            "account_disabled",
                            "account_deleted",
                            "refresh_reused",
                            "confirmation_failed",
                            "admin_revoked",
                        ]
                    )
                ),
                name="auth_session_revoke_reason_valid",
            ),
            models.CheckConstraint(
                condition=(
                    (models.Q(status="revoked", revoked_at__isnull=False) & ~models.Q(revoke_reason=""))
                    | models.Q(
                        status__in=["active", "refresh_confirmation_required"],
                        revoked_at__isnull=True,
                        revoke_reason="",
                    )
                ),
                name="auth_session_state_consistent",
            ),
        ]

    @property
    def is_revoked(self):
        return self.status == self.Status.REVOKED

    def is_expired(self, at=None):
        return self.absolute_expires_at <= (at or timezone.now())
