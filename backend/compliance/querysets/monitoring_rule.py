from django.db.models import QuerySet

from compliance.constants import (
    RULE_TYPE_AGGREGATE_VOLUME,
    RULE_TYPE_PATTERN,
    RULE_TYPE_RAPID_TRANSACTIONS,
    RULE_TYPE_ROUND_AMOUNTS,
)


class MonitoringRuleQuerySet(QuerySet):
    def active(self):
        return self.filter(is_active=True)

    def pattern_rules(self):
        return self.filter(
            rule_type__in=[
                RULE_TYPE_RAPID_TRANSACTIONS,
                RULE_TYPE_PATTERN,
                RULE_TYPE_AGGREGATE_VOLUME,
                RULE_TYPE_ROUND_AMOUNTS,
            ]
        )
