"""
Remove the preferred_onramp_provider field entirely.

The field is no longer used — the on-ramp system was simplified to
Transak-only and no provider preference is needed.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0009_remove_banxa_coinbase_onramp_provider"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="userpreferences",
            name="preferred_onramp_provider",
        ),
    ]
