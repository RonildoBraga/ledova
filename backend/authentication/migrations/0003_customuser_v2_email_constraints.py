from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import migrations, models

import authentication.email

V2_EMAIL_PREFLIGHT_ERROR = "V2 email migration preflight failed."


def _normalize_v2_email(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 254:
        raise RuntimeError(V2_EMAIL_PREFLIGHT_ERROR)
    if any(ord(character) < 0x20 or ord(character) > 0x7E for character in value):
        raise RuntimeError(V2_EMAIL_PREFLIGHT_ERROR)
    normalized = value.strip(" ").lower()
    try:
        validate_email(normalized)
    except ValidationError:
        raise RuntimeError(V2_EMAIL_PREFLIGHT_ERROR) from None
    return normalized


def lock_and_preflight_v2_email(apps, schema_editor):
    connection = schema_editor.connection
    if not connection.in_atomic_block:
        raise RuntimeError(V2_EMAIL_PREFLIGHT_ERROR)
    user_model = apps.get_model("authentication", "CustomUser")
    table = schema_editor.quote_name(user_model._meta.db_table)
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute(f"LOCK TABLE {table} IN ACCESS EXCLUSIVE MODE")
    elif connection.vendor == "sqlite":
        primary_key = schema_editor.quote_name(user_model._meta.pk.column)
        with connection.cursor() as cursor:
            cursor.execute(f"UPDATE {table} SET {primary_key} = {primary_key} WHERE 0")
    else:
        raise RuntimeError(V2_EMAIL_PREFLIGHT_ERROR)

    seen = set()
    emails = user_model._base_manager.using(connection.alias).order_by().values_list("email", flat=True)
    try:
        for email in emails.iterator(chunk_size=1000):
            normalized = _normalize_v2_email(email)
            if normalized != email or normalized in seen:
                raise RuntimeError(V2_EMAIL_PREFLIGHT_ERROR)
            seen.add(normalized)
    except RuntimeError:
        raise RuntimeError(V2_EMAIL_PREFLIGHT_ERROR) from None


class Migration(migrations.Migration):
    atomic = True

    dependencies = [
        ("authentication", "0002_authsession_refreshcredential"),
    ]

    operations = [
        migrations.RunPython(lock_and_preflight_v2_email, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="customuser",
            constraint=models.CheckConstraint(
                condition=authentication.email.EmailIsPrintableASCII(models.F("email")),
                name="auth_user_email_v2_ascii_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="customuser",
            constraint=models.CheckConstraint(
                condition=models.Q(email=authentication.email.EmailDestinationKey(models.F("email"))),
                name="auth_user_email_v2_canon_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="customuser",
            constraint=models.UniqueConstraint(
                authentication.email.EmailDestinationKey(models.F("email")),
                name="auth_user_email_v2_key_uniq",
            ),
        ),
    ]
