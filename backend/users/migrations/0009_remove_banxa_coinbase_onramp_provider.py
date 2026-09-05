from django.db import migrations, models


def clear_removed_providers(apps, schema_editor):
    UserPreferences = apps.get_model("users", "UserPreferences")
    UserPreferences.objects.filter(preferred_onramp_provider__in=["banxa", "coinbase"]).update(
        preferred_onramp_provider=None
    )


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0008_alter_userprofile_sumsub_review_answer_and_more"),
    ]

    operations = [
        migrations.RunPython(clear_removed_providers, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="userpreferences",
            name="preferred_onramp_provider",
            field=models.CharField(
                blank=True,
                choices=[("transak", "Transak")],
                help_text="User's preferred fiat on-ramp provider for buying crypto",
                max_length=20,
                null=True,
            ),
        ),
    ]
