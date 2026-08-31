from django.contrib import admin
from django.utils.html import format_html

from companies.models import ApplicationReview, ReviewDecision, ReviewNote


class ReviewNoteInline(admin.TabularInline):
    model = ReviewNote
    extra = 0
    fields = ["author", "content", "visible_to_company", "created_at"]
    readonly_fields = ["created_at"]


@admin.register(ApplicationReview)
class ApplicationReviewAdmin(admin.ModelAdmin):
    list_display = [
        "company",
        "reviewer",
        "review_order",
        "decision_badge",
        "assigned_at",
        "decision_at",
    ]
    list_filter = ["decision", "review_order", "assigned_at"]
    search_fields = ["company__name", "reviewer__email"]
    readonly_fields = ["uuid", "assigned_at", "decision_at", "created_at", "updated_at"]
    list_select_related = ["company", "reviewer"]
    inlines = [ReviewNoteInline]

    fieldsets = [
        (
            "Review Assignment",
            {
                "fields": [
                    "uuid",
                    "company",
                    "reviewer",
                    "review_order",
                    "assigned_by",
                    "assigned_at",
                ]
            },
        ),
        (
            "Decision",
            {
                "fields": [
                    "decision",
                    "decision_at",
                    "decision_reason",
                ]
            },
        ),
        (
            "Notes",
            {
                "fields": [
                    "notes",
                ],
                "classes": ["collapse"],
            },
        ),
        (
            "Timestamps",
            {
                "fields": [
                    "created_at",
                    "updated_at",
                ],
                "classes": ["collapse"],
            },
        ),
    ]

    def decision_badge(self, obj):
        colors = {
            ReviewDecision.PENDING: "#6c757d",
            ReviewDecision.APPROVED: "#28a745",
            ReviewDecision.REJECTED: "#dc3545",
            ReviewDecision.RECUSED: "#17a2b8",
        }
        color = colors.get(obj.decision, "#777777")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px;">{}</span>',
            color,
            obj.get_decision_display(),
        )

    decision_badge.short_description = "Decision"
    decision_badge.admin_order_field = "decision"


@admin.register(ReviewNote)
class ReviewNoteAdmin(admin.ModelAdmin):
    list_display = [
        "review",
        "author",
        "visibility_badge",
        "content_preview",
        "created_at",
    ]
    list_filter = ["visible_to_company", "created_at"]
    search_fields = ["review__company__name", "author__email", "content"]
    readonly_fields = ["uuid", "created_at", "updated_at"]
    list_select_related = ["review", "review__company", "author"]

    def visibility_badge(self, obj):
        if obj.visible_to_company:
            return format_html(
                '<span style="background-color: #28a745; color: white; padding: 2px 6px; '
                'border-radius: 3px; font-size: 10px;">External</span>'
            )
        return format_html(
            '<span style="background-color: #6c757d; color: white; padding: 2px 6px; '
            'border-radius: 3px; font-size: 10px;">Internal</span>'
        )

    visibility_badge.short_description = "Visibility"

    def content_preview(self, obj):
        if len(obj.content) > 50:
            return f"{obj.content[:50]}..."
        return obj.content

    content_preview.short_description = "Content"
