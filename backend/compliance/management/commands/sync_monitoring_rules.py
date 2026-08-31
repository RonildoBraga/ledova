"""
Management command to sync monitoring rules.

This command ensures all required monitoring rules exist in the database.
It uses update_or_create to be idempotent - safe to run multiple times.

Usage:
    python manage.py sync_monitoring_rules
    python manage.py sync_monitoring_rules --verbosity 2  # Show details
"""

from django.core.management.base import BaseCommand

from compliance.models import MonitoringRule


class Command(BaseCommand):
    help = "Sync monitoring rules to the database (idempotent)"

    def handle(self, *args, **options):
        verbosity = options.get("verbosity", 1)

        rules = self.get_rules()
        valid_rule_codes = {r["rule_code"] for r in rules}

        created_count = 0
        updated_count = 0

        for rule_data in rules:
            rule_code = rule_data.pop("rule_code")
            obj, created = MonitoringRule.objects.update_or_create(
                rule_code=rule_code,
                defaults=rule_data,
            )

            if created:
                created_count += 1
                if verbosity >= 2:
                    self.stdout.write(f"  Created: {rule_code} - {obj.name}")
            else:
                updated_count += 1
                if verbosity >= 2:
                    self.stdout.write(f"  Updated: {rule_code} - {obj.name}")

        # Remove rules not in the defined list
        obsolete_rules = MonitoringRule.objects.exclude(rule_code__in=valid_rule_codes)
        deleted_count = obsolete_rules.count()
        if deleted_count > 0:
            if verbosity >= 2:
                for rule in obsolete_rules:
                    self.stdout.write(f"  Deleted: {rule.rule_code} - {rule.name}")
            obsolete_rules.delete()

        if verbosity >= 1:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Sync complete: {created_count} created, {updated_count} updated, {deleted_count} deleted"
                )
            )

    def get_rules(self):
        """Return list of all monitoring rules."""
        return [
            # =================================================================
            # Core Transaction Monitoring Rules (MON-001 to MON-006)
            # =================================================================
            {
                "rule_code": "MON-001",
                "name": "Large Transaction",
                "description": "Transaction >= AUD 10,000 requires compliance review",
                "rule_type": "threshold",
                "parameters": {"amount": 10000, "currency": "AUD"},
                "alert_severity": "medium",
                "is_active": True,
            },
            {
                "rule_code": "MON-002",
                "name": "Rapid Transactions",
                "description": "5 or more transactions within 1 hour",
                "rule_type": "rapid_transactions",
                "parameters": {"max_transactions": 5, "period_minutes": 60},
                "alert_severity": "high",
                "is_active": True,
            },
            {
                "rule_code": "MON-003",
                "name": "Structuring Pattern",
                "description": "Multiple transactions just below AUD 10,000 threshold (potential structuring)",
                "rule_type": "pattern",
                "parameters": {
                    "min_transactions": 3,
                    "min_each": 8000,
                    "max_each": 9999,
                    "period_hours": 168,
                    "currency": "AUD",
                },
                "alert_severity": "high",
                "is_active": True,
            },
            {
                "rule_code": "MON-004",
                "name": "High-Risk Wallet",
                "description": "Transaction involving flagged blockchain address",
                "rule_type": "address",
                "parameters": {"check_type": "high_risk_wallet"},
                "alert_severity": "high",
                "is_active": True,
            },
            {
                "rule_code": "MON-005",
                "name": "Sanctioned Address",
                "description": "Transaction involving address on sanctions list",
                "rule_type": "address",
                "parameters": {"check_type": "sanctioned"},
                "alert_severity": "critical",
                "is_active": True,
            },
            {
                "rule_code": "MON-006",
                "name": "New Customer SOF",
                "description": "New customer transaction >= AUD 10,000 requires source of funds documentation",
                "rule_type": "sof_required",
                "parameters": {"amount": 10000, "currency": "AUD", "customer_age_days": 30},
                "alert_severity": "high",
                "is_active": True,
            },
            # =================================================================
            # Advanced Monitoring Rules (MON-007 to MON-010)
            # Policy References: Document 3 §3.1, Document 5 §3.2
            # =================================================================
            {
                "rule_code": "MON-007",
                "name": "High Aggregate Volume",
                "description": "Cumulative transaction volume >= AUD 50,000 in 30 days",
                "rule_type": "aggregate_volume",
                "parameters": {"amount": 50000, "period_days": 30, "currency": "AUD"},
                "alert_severity": "medium",
                "is_active": True,
            },
            {
                "rule_code": "MON-008",
                "name": "Dormant Account Reactivation",
                "description": "Significant transaction (>= AUD 5,000) after 90+ days of inactivity",
                "rule_type": "dormant_reactivation",
                "parameters": {"dormant_days": 90, "min_amount": 5000, "currency": "AUD"},
                "alert_severity": "medium",
                "is_active": True,
            },
            {
                "rule_code": "MON-009",
                "name": "Material Pattern Deviation",
                "description": "Transaction 3x or more the customer's 90-day average (requires 5+ prior transactions)",
                "rule_type": "pattern_deviation",
                "parameters": {"multiplier": 3, "min_history": 5, "baseline_days": 90},
                "alert_severity": "medium",
                "is_active": True,
            },
            {
                "rule_code": "MON-010",
                "name": "Round Amount Transactions",
                "description": "3+ transactions divisible by $5,000 in 30 days (potential structuring indicator)",
                "rule_type": "round_amounts",
                "parameters": {"count": 3, "period_days": 30, "divisor": 5000, "min_amount": 1000},
                "alert_severity": "low",
                "is_active": True,
            },
            # =================================================================
            # Risk-Based Monitoring Rules (MON-011)
            # Policy References: Document 2 §4.2
            # =================================================================
            {
                "rule_code": "MON-011",
                "name": "Extreme Risk Customer",
                "description": "Any transaction by EXTREME risk customer requires manual review (Document 2 §4.2)",
                "rule_type": "extreme_risk",
                "parameters": {},
                "alert_severity": "critical",
                "is_active": True,
            },
        ]
