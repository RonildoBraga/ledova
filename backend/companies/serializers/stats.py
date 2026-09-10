from rest_framework import serializers


class CompanyStatsSerializer(serializers.Serializer):
    total_tokens = serializers.IntegerField()
    total_shareholders = serializers.IntegerField()
    pending_actions = serializers.IntegerField()
    pending_capital_increases = serializers.IntegerField()
