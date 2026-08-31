"""Add provider-agnostic KYC fields and KYCAID fields to UserProfile."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0004_create_notification_model"),
    ]

    operations = [
        # Provider-agnostic fields
        migrations.AddField(
            model_name="userprofile",
            name="kyc_provider",
            field=models.CharField(
                choices=[("sumsub", "Sumsub"), ("kycaid", "KYCAID")],
                default="kycaid",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="verification_status",
            field=models.CharField(
                blank=True,
                choices=[
                    ("init", "Initialized"),
                    ("pending", "Pending Review"),
                    ("queued", "Queued for Review"),
                    ("completed", "Review Completed"),
                    ("onHold", "On Hold"),
                    ("prechecked", "Pre-checked"),
                ],
                max_length=50,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="review_result",
            field=models.CharField(
                blank=True,
                choices=[
                    ("GREEN", "Approved"),
                    ("RED", "Rejected"),
                    ("YELLOW", "Retry"),
                ],
                max_length=20,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="rejection_labels",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="verified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        # KYCAID-specific fields
        migrations.AddField(
            model_name="userprofile",
            name="kycaid_applicant_id",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="kycaid_verification_id",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
    ]
