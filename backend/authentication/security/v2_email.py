from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db.models import CharField, F, Func
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
