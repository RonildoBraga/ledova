from django.contrib import admin

from documents.models import DocumentExtraction, ExtractionStatus


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
    actions = ("rerun_extraction",)

    @admin.action(description="Re-run extraction for the selected failed attempts")
    def rerun_extraction(self, request, queryset):
        from documents.tasks import extract_document

        failed = queryset.filter(status=ExtractionStatus.FAILED)
        if not failed.exists():
            self.message_user(
                request,
                "No failed extraction selected. Only a failed attempt can be re-run.",
                level="warning",
            )
            return

        documents = sorted({str(uuid) for uuid in failed.values_list("document__uuid", flat=True)})
        for document_uuid in documents:
            extract_document.defer(document_uuid=document_uuid)
        self.message_user(request, f"Queued {len(documents)} document(s) for re-extraction.")

    def has_add_permission(self, request) -> bool:

        return False
