from rest_framework import serializers

from authentication.security.v2_email import V2EmailError, normalize_v2_email


class V2EmailField(serializers.CharField):
    default_error_messages = {"invalid": "Enter a valid email address."}

    def __init__(self, **kwargs):
        kwargs.setdefault("max_length", 254)
        kwargs.setdefault("trim_whitespace", False)
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        try:
            return normalize_v2_email(data)
        except V2EmailError:
            self.fail("invalid")
