from django.contrib import admin

from documents.models import DocumentExtraction


@admin.register(DocumentExtraction)
class DocumentExtractionAdmin(admin.ModelAdmin):
    list_display = ("uuid", "document", "status", "model_name", "confidence", "duration_ms", "created_at")
    list_filter = ("status", "model_name", "created_at")
    search_fields = ("document__original_filename", "document__uploaded_by__email", "error")
    readonly_fields = (
        "uuid",
        "document",
        "status",
        "model_name",
        "raw_output",
        "parsed_json",
        "confidence",
        "warnings",
        "error",
        "duration_ms",
        "started_at",
        "finished_at",
        "created_at",
        "updated_at",
    )
    ordering = ("-created_at",)

    def has_add_permission(self, request) -> bool:

        return False
