from django.db import migrations


def populate_generic_fields(apps, schema_editor):
    UserProfile = apps.get_model("users", "UserProfile")

    profiles_with_sumsub = UserProfile.objects.filter(
        sumsub_applicant_id__isnull=False,
    ).exclude(sumsub_applicant_id="")

    for profile in profiles_with_sumsub.iterator():
        profile.kyc_provider = "sumsub"
        profile.verification_status = profile.sumsub_verification_status
        profile.review_result = profile.sumsub_review_result
        profile.rejection_labels = profile.sumsub_rejection_labels
        profile.verified_at = profile.sumsub_verified_at
        profile.save(
            update_fields=[
                "kyc_provider",
                "verification_status",
                "review_result",
                "rejection_labels",
                "verified_at",
            ]
        )


def reverse_populate(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0005_add_kyc_provider_fields"),
    ]

    operations = [
        migrations.RunPython(populate_generic_fields, reverse_populate),
    ]
