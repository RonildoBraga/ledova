from rest_framework import serializers

from authentication.email import EmailError, normalize_email


class NormalizedEmailField(serializers.CharField):
    default_error_messages = {"invalid": "Enter a valid email address."}

    def __init__(self, **kwargs):
        kwargs.setdefault("max_length", 254)
        kwargs.setdefault("trim_whitespace", False)
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        try:
            return normalize_email(data)
        except EmailError:
            self.fail("invalid")
