from rest_framework import serializers

from tokens.models import FormerHolder
from tokens.models.choices import IDENTITY_LABELS


class FormerMemberSerializer(serializers.ModelSerializer):

    identity_source_display = serializers.SerializerMethodField()

    class Meta:
        model = FormerHolder
        fields = [
            "uuid",
            "wallet_address",
            "name",
            "residential_address",
            "shares_at_cessation",
            "ceased_on",
            "ceased_at_block",
            "identity_source",
            "identity_source_display",
        ]
        read_only_fields = fields

    def get_identity_source_display(self, instance) -> str:
        return IDENTITY_LABELS.get(instance.identity_source, instance.identity_source)
