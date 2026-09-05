from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0016_remove_userprofile_duplicate_kyc_columns"),
    ]

    operations = [
        migrations.DeleteModel(
            name="Waitlist",
        ),
    ]
