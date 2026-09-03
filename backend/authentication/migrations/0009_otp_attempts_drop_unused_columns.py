from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("authentication", "0008_delete_usertoken"),
    ]

    operations = [
        migrations.AddField(
            model_name="customuser",
            name="email_verification_attempts",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.RemoveField(model_name="customuser", name="sms_verification_token"),
        migrations.RemoveField(model_name="customuser", name="sms_verification_sent_at"),
        migrations.RemoveField(model_name="customuser", name="is_phone_verified"),
        migrations.RemoveField(model_name="customuser", name="password_reset_token"),
        migrations.RemoveField(model_name="customuser", name="password_reset_sent_at"),
    ]
