from rest_framework import serializers

from tokens.models import FormerHolder
from tokens.models.choices import IDENTITY_LABELS, IDENTITY_LIVE


class FormerMemberSerializer(serializers.ModelSerializer):

    identity_source_display = serializers.SerializerMethodField()
    identity_recorded_at = serializers.DateTimeField(source="created_at", read_only=True)

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
            "identity_recorded_at",
        ]
        read_only_fields = fields

    def get_identity_source_display(self, instance) -> str:
        if instance.identity_source == IDENTITY_LIVE:
            return "Profile when the cessation was recorded"
        return IDENTITY_LABELS.get(instance.identity_source, instance.identity_source)
