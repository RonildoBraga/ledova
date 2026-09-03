from django.contrib import admin

from compliance.admin._helpers import GREY, RED, TEAL, admin_link, badge
from compliance.models import AlertProcedureStep


@admin.register(AlertProcedureStep)
class AlertProcedureStepAdmin(admin.ModelAdmin):
    list_display = [
        "order",
        "description_truncated",
        "template_link",
        "is_required_badge",
        "is_conditional_badge",
        "policy_reference",
    ]
    list_filter = ["is_required", ("template", admin.RelatedOnlyFieldListFilter)]
    search_fields = ["description", "detailed_instructions", "template__name", "template__alert_type"]
    readonly_fields = ["uuid", "created_at", "updated_at"]
    ordering = ["template", "order"]
    autocomplete_fields = ["template"]

    @admin.display(description="Description", ordering="description")
    def description_truncated(self, obj):
        return obj.description[:60] + "..." if len(obj.description) > 60 else obj.description

    @admin.display(description="Template", ordering="template__name")
    def template_link(self, obj):
        return admin_link(obj.template, obj.template.name[:30])

    @admin.display(description="Required", ordering="is_required")
    def is_required_badge(self, obj):
        return badge("REQUIRED", RED) if obj.is_required else badge("OPTIONAL", GREY)

    @admin.display(description="Conditional")
    def is_conditional_badge(self, obj):
        return badge("CONDITIONAL", TEAL, title=obj.condition) if obj.is_conditional else "-"
