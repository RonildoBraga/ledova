"""Idempotent loader for compliance/seeds/monitoring_rules.py; safe to run repeatedly."""

from django.core.management.base import BaseCommand

from compliance.models import MonitoringRule
from compliance.seeds.monitoring_rules import MONITORING_RULES


class Command(BaseCommand):
    help = "Sync monitoring rules to the database (idempotent)"

    def handle(self, *args, **options):
        verbosity = options["verbosity"]
        created = updated = 0
        for rule in MONITORING_RULES:
            defaults = {key: value for key, value in rule.items() if key != "rule_code"}
            obj, was_created = MonitoringRule.objects.update_or_create(rule_code=rule["rule_code"], defaults=defaults)
            created += was_created
            updated += not was_created
            if verbosity >= 2:
                self.stdout.write(f"  {'Created' if was_created else 'Updated'}: {obj.rule_code} - {obj.name}")

        obsolete = MonitoringRule.objects.exclude(rule_code__in=[rule["rule_code"] for rule in MONITORING_RULES])
        deleted = obsolete.count()
        if verbosity >= 2:
            for rule in obsolete:
                self.stdout.write(f"  Deleted: {rule.rule_code} - {rule.name}")
        obsolete.delete()

        if verbosity >= 1:
            self.stdout.write(
                self.style.SUCCESS(f"Sync complete: {created} created, {updated} updated, {deleted} deleted")
            )
