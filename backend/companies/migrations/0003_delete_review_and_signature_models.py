from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("companies", "0002_company_owner_required"),
        ("tokens", "0013_remove_transferorder_signature_request"),
    ]

    operations = [
        migrations.DeleteModel(name="ReviewNote"),
        migrations.DeleteModel(name="ApplicationReview"),
        migrations.DeleteModel(name="SignatureRequest"),
    ]
