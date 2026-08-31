"""
Admin for AlertProcedureStep model.
"""

from django.contrib import admin
from django.utils.html import format_html

from compliance.models import AlertProcedureStep


@admin.register(AlertProcedureStep)
class AlertProcedureStepAdmin(admin.ModelAdmin):
    """
    Admin for alert procedure steps.

    Allows AML Compliance Officer to:
    - Define individual steps within procedure templates
    - Configure step requirements and conditions
    - Add detailed instructions and policy references
    """

    list_display = [
        "order",
        "description_truncated",
        "template_link",
        "is_required_badge",
        "is_conditional_badge",
        "policy_reference",
    ]
    list_filter = [
        "is_required",
        ("template", admin.RelatedOnlyFieldListFilter),
    ]
    search_fields = [
        "description",
        "detailed_instructions",
        "template__name",
        "template__alert_type",
    ]
    readonly_fields = [
        "uuid",
        "created_at",
        "updated_at",
    ]
    ordering = ["template", "order"]
    autocomplete_fields = ["template"]

    fieldsets = (
        (
            "Step Information",
            {
                "fields": (
                    "template",
                    "order",
                    "description",
                    "detailed_instructions",
                ),
            },
        ),
        (
            "Requirements",
            {
                "fields": (
                    "is_required",
                    "condition",
                ),
            },
        ),
        (
            "Help & References",
            {
                "fields": (
                    "help_text",
                    "policy_reference",
                ),
            },
        ),
        (
            "System Information",
            {
                "fields": ("uuid", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def description_truncated(self, obj):
        """Truncate description for list display."""
        return obj.description[:60] + "..." if len(obj.description) > 60 else obj.description

    description_truncated.short_description = "Description"
    description_truncated.admin_order_field = "description"

    def template_link(self, obj):
        """Link to the parent template."""
        return format_html(
            '<a href="/admin/compliance/alertproceduretemplate/{}/change/">{}</a>',
            obj.template.uuid,
            obj.template.name[:30],
        )

    template_link.short_description = "Template"
    template_link.admin_order_field = "template__name"

    def is_required_badge(self, obj):
        """Display required status as a badge."""
        if obj.is_required:
            return format_html(
                '<span style="background-color: #dc3545; color: white; padding: 2px 8px; '
                'border-radius: 4px; font-size: 11px;">REQUIRED</span>'
            )
        return format_html(
            '<span style="background-color: #6c757d; color: white; padding: 2px 8px; '
            'border-radius: 4px; font-size: 11px;">OPTIONAL</span>'
        )

    is_required_badge.short_description = "Required"
    is_required_badge.admin_order_field = "is_required"

    def is_conditional_badge(self, obj):
        """Display conditional status."""
        if obj.is_conditional:
            return format_html(
                '<span title="{}" style="background-color: #17a2b8; color: white; padding: 2px 8px; '
                'border-radius: 4px; font-size: 11px;">CONDITIONAL</span>',
                obj.condition,
            )
        return "-"

    is_conditional_badge.short_description = "Conditional"
