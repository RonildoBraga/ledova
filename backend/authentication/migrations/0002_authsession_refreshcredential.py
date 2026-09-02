import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("authentication", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="AuthSession",
            fields=[
                (
                    "uuid",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        help_text="Unique identifier (primary key)",
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "client_type",
                    models.CharField(
                        choices=[("browser", "Browser"), ("native", "Native")],
                        max_length=16,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("active", "Active"),
                            ("refresh_confirmation_required", "Refresh confirmation required"),
                            ("revoked", "Revoked"),
                        ],
                        default="active",
                        max_length=32,
                    ),
                ),
                ("device_label", models.CharField(blank=True, default="", max_length=80)),
                ("absolute_expires_at", models.DateTimeField()),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                (
                    "revoke_reason",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("signed_out", "Signed out"),
                            ("signed_out_all", "Signed out everywhere"),
                            ("password_change", "Password changed"),
                            ("password_reset", "Password reset"),
                            ("email_change", "Email changed"),
                            ("account_disabled", "Account disabled"),
                            ("account_deleted", "Account deleted"),
                            ("refresh_reused", "Refresh reused"),
                            ("confirmation_failed", "Confirmation failed"),
                            ("admin_revoked", "Administrator revoked"),
                        ],
                        default="",
                        max_length=32,
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="auth_sessions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="RefreshCredential",
            fields=[
                (
                    "uuid",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        help_text="Unique identifier (primary key)",
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("secret_digest", models.BinaryField(max_length=32)),
                ("expires_at", models.DateTimeField()),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                (
                    "confirmation_nonce_digest",
                    models.BinaryField(blank=True, max_length=32, null=True),
                ),
                ("confirmation_expires_at", models.DateTimeField(blank=True, null=True)),
                ("confirmation_consumed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "replaced_by",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.RESTRICT,
                        related_name="predecessor",
                        to="authentication.refreshcredential",
                    ),
                ),
                (
                    "session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="refresh_credentials",
                        to="authentication.authsession",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="authsession",
            index=models.Index(
                fields=["user", "status", "-created_at"],
                name="auth_sess_user_state_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="authsession",
            index=models.Index(
                fields=["status", "absolute_expires_at"],
                name="auth_sess_expiry_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="authsession",
            constraint=models.CheckConstraint(
                condition=models.Q(client_type__in=["browser", "native"]),
                name="auth_session_client_type_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="authsession",
            constraint=models.CheckConstraint(
                condition=models.Q(revoke_reason="")
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
                ),
                name="auth_session_revoke_reason_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="authsession",
            constraint=models.CheckConstraint(
                condition=(
                    (models.Q(revoked_at__isnull=False, status="revoked") & ~models.Q(revoke_reason=""))
                    | models.Q(
                        revoke_reason="",
                        revoked_at__isnull=True,
                        status__in=["active", "refresh_confirmation_required"],
                    )
                ),
                name="auth_session_state_consistent",
            ),
        ),
        migrations.AddIndex(
            model_name="refreshcredential",
            index=models.Index(
                fields=["session", "-created_at"],
                name="auth_ref_session_created_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="refreshcredential",
            index=models.Index(fields=["expires_at"], name="auth_ref_expires_idx"),
        ),
        migrations.AddIndex(
            model_name="refreshcredential",
            index=models.Index(
                fields=["confirmation_expires_at"],
                name="auth_ref_confirm_exp_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="refreshcredential",
            constraint=models.UniqueConstraint(
                condition=models.Q(revoked_at__isnull=True, used_at__isnull=True),
                fields=("session",),
                name="auth_ref_one_live_per_session",
            ),
        ),
        migrations.AddConstraint(
            model_name="refreshcredential",
            constraint=models.UniqueConstraint(
                condition=models.Q(confirmation_nonce_digest__isnull=False),
                fields=("session",),
                name="auth_ref_one_confirmation_per_session",
            ),
        ),
        migrations.AddConstraint(
            model_name="refreshcredential",
            constraint=models.CheckConstraint(
                condition=models.Q(replaced_by__isnull=True) | models.Q(used_at__isnull=False),
                name="auth_ref_successor_spent",
            ),
        ),
        migrations.AddConstraint(
            model_name="refreshcredential",
            constraint=models.CheckConstraint(
                condition=~models.Q(uuid=models.F("replaced_by")),
                name="auth_ref_successor_not_self",
            ),
        ),
        migrations.AddConstraint(
            model_name="refreshcredential",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        confirmation_consumed_at__isnull=True,
                        confirmation_expires_at__isnull=True,
                        confirmation_nonce_digest__isnull=True,
                    )
                    | models.Q(
                        confirmation_expires_at__isnull=False,
                        confirmation_nonce_digest__isnull=False,
                        replaced_by__isnull=False,
                        used_at__isnull=False,
                    )
                ),
                name="auth_ref_confirmation_state",
            ),
        ),
    ]
