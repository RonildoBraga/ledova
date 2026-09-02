from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import NotSupportedError
from django.db.models import BooleanField, CharField, F, Func
from django.db.models.functions import Trim

EMAIL_ERROR = "Invalid email address."


class EmailError(ValueError):
    pass


class EmailDestinationKey(Func):
    function = "LOWER"
    arity = 1
    output_field = CharField()

    def __init__(self, expression):
        super().__init__(Trim(expression))

    def as_postgresql(self, compiler, connection, **extra_context):
        return super().as_sql(
            compiler,
            connection,
            template='%(function)s(%(expressions)s COLLATE "C")',
            **extra_context,
        )


class EmailIsPrintableASCII(Func):
    arity = 1
    output_field = BooleanField()

    def as_postgresql(self, compiler, connection, **extra_context):
        expression, params = compiler.compile(self.source_expressions[0])
        collation = connection.ops.quote_name("C")
        return (
            f"(CHAR_LENGTH({expression}) BETWEEN 1 AND 254 " f"AND ({expression} COLLATE {collation}) !~ %s)",
            (*params, *params, r"[^ -~]"),
        )

    def as_sqlite(self, compiler, connection, **extra_context):
        expression, params = compiler.compile(self.source_expressions[0])
        return (
            f"(LENGTH(CAST({expression} AS BLOB)) BETWEEN 1 AND 254 "
            f"AND LENGTH(CAST({expression} AS BLOB)) = LENGTH({expression}) "
            f"AND {expression} NOT GLOB %s)",
            (*params, *params, *params, *params, r"*[^ -~]*"),
        )

    def as_sql(self, compiler, connection, **extra_context):
        raise NotSupportedError("Email constraints support PostgreSQL and SQLite only.")


def normalize_email(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 254:
        raise EmailError(EMAIL_ERROR)
    if any(ord(character) < 0x20 or ord(character) > 0x7E for character in value):
        raise EmailError(EMAIL_ERROR)

    normalized = value.strip(" ").lower()
    try:
        validate_email(normalized)
    except ValidationError:
        raise EmailError(EMAIL_ERROR) from None
    return normalized


def email_destination_expression(field_name="email"):
    return EmailDestinationKey(F(field_name))
