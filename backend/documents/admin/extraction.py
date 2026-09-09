from django.contrib import admin

from documents.admin.access import AuditsDocumentReads
from documents.models import Document, DocumentExtraction, ExtractionStatus


@admin.register(DocumentExtraction)
class DocumentExtractionAdmin(AuditsDocumentReads, admin.ModelAdmin):
    read_kind = "extraction"
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

    def document_for_read(self, obj):
        return obj.document

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .filter(document__in=Document.objects.with_available_content())
            .select_related("document__classification")
        )

    def has_change_permission(self, request, obj=None):
        return self.has_view_permission(request, obj) and super().has_change_permission(request, obj)

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
