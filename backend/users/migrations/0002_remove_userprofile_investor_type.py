# Generated manually - Remove InvestorType field from UserProfile

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="userprofile",
            name="investor_type",
        ),
    ]
