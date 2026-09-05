from django.core.management.base import BaseCommand
from django.db import transaction

from compliance.models import AlertProcedureStep, AlertProcedureTemplate
from compliance.seeds.procedure_templates import PROCEDURE_TEMPLATES


class Command(BaseCommand):
    help = "Sync alert procedure templates to the database (idempotent)"

    @transaction.atomic
    def handle(self, *args, **options):
        verbosity = options["verbosity"]
        created = updated = steps_created = steps_updated = 0

        for template in PROCEDURE_TEMPLATES:
            defaults = {key: value for key, value in template.items() if key not in ("alert_type", "steps")}
            obj, was_created = AlertProcedureTemplate.objects.update_or_create(
                alert_type=template["alert_type"], defaults=defaults
            )
            created += was_created
            updated += not was_created
            if verbosity >= 2:
                self.stdout.write(
                    f"  {'Created' if was_created else 'Updated'} template: {obj.alert_type} - {obj.name}"
                )

            for step in template["steps"]:
                step_defaults = {key: value for key, value in step.items() if key != "order"}
                step_obj, step_was_created = AlertProcedureStep.objects.update_or_create(
                    template=obj, order=step["order"], defaults=step_defaults
                )
                steps_created += step_was_created
                steps_updated += not step_was_created
                if verbosity >= 3:
                    verb = "Created" if step_was_created else "Updated"
                    self.stdout.write(f"    {verb} step {step_obj.order}: {step_obj.description[:50]}")

            obsolete_steps = obj.steps.exclude(order__in=[step["order"] for step in template["steps"]])
            if verbosity >= 2:
                for step in obsolete_steps:
                    self.stdout.write(f"    Deleted step {step.order}: {step.description[:50]}")
            obsolete_steps.delete()

        obsolete = AlertProcedureTemplate.objects.exclude(
            alert_type__in=[template["alert_type"] for template in PROCEDURE_TEMPLATES]
        )
        deleted = obsolete.count()
        if verbosity >= 2:
            for template in obsolete:
                self.stdout.write(f"  Deleted template: {template.alert_type} - {template.name}")
        obsolete.delete()

        if verbosity >= 1:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Templates: {created} created, {updated} updated, {deleted} deleted | "
                    f"Steps: {steps_created} created, {steps_updated} updated"
                )
            )
