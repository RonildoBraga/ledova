from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import NotSupportedError
from django.db.models import BooleanField, CharField, F, Func
from django.db.models.functions import Trim

V2_EMAIL_ERROR = "Invalid v2 email address."


class V2EmailError(ValueError):
    pass


class V2EmailDestinationKey(Func):
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


class V2EmailIsPrintableASCII(Func):
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
        raise NotSupportedError("V2 email constraints support PostgreSQL and SQLite only.")


def normalize_v2_email(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 254:
        raise V2EmailError(V2_EMAIL_ERROR)
    if any(ord(character) < 0x20 or ord(character) > 0x7E for character in value):
        raise V2EmailError(V2_EMAIL_ERROR)

    normalized = value.strip(" ").lower()
    try:
        validate_email(normalized)
    except ValidationError:
        raise V2EmailError(V2_EMAIL_ERROR) from None
    return normalized


def v2_email_destination_expression(field_name="email"):
    return V2EmailDestinationKey(F(field_name))
