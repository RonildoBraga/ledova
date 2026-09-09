from django.contrib import admin
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.html import format_html

from documents.admin.access import AuditsDocumentReads
from documents.models import Document
from documents.services.access import record_document_read
from shared.utils.admin_files import admin_file_path


@admin.register(Document)
class DocumentAdmin(AuditsDocumentReads, admin.ModelAdmin):
    list_display = ("uuid", "uploaded_by", "classification", "document_type", "original_filename", "created_at")
    list_filter = ("document_type", "created_at")
    search_fields = ("uploaded_by__email", "original_filename", "note")
    readonly_fields = (
        "uuid",
        "uploaded_by",
        "classification",
        "attached_at",
        "retention_until",
        "document_type",
        "note",
        "file_link",
        "extraction_links",
        "original_filename",
        "mime_type",
        "created_at",
        "updated_at",
    )
    raw_id_fields = ("uploaded_by",)
    ordering = ("-created_at",)

    fieldsets = [
        ("Document", {"fields": ["uploaded_by", "document_type", "note"]}),
        ("Supporting evidence", {"fields": ["classification", "attached_at", "retention_until", "extraction_links"]}),
        ("File", {"fields": ["file_link", "original_filename", "mime_type"]}),
        ("Timestamps", {"fields": ["uuid", "created_at", "updated_at"], "classes": ["collapse"]}),
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).with_available_content().select_related("classification", "uploaded_by")

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description="Extraction (requires human review)")
    def extraction_links(self, obj):
        from django.utils.html import format_html_join

        return (
            format_html_join(
                " ",
                '<a href="{}">{} — review extraction</a>',
                (
                    (reverse("admin:documents_documentextraction_change", args=[row.pk]), row.get_status_display())
                    for row in obj.extractions.all()
                ),
            )
            or "No extraction recorded"
        )

    @admin.display(description="File")
    def file_link(self, obj):
        if obj.pk is None or not obj.file:
            return "-"
        url = reverse("admin:documents_document_file", args=[obj.uuid])
        return format_html('<a href="{}" target="_blank">Open document</a>', url)

    def get_urls(self):
        custom_urls = [
            admin_file_path(self, "<uuid:uuid>/file/", "documents_document_file", self._resolve_file),
        ]
        return custom_urls + super().get_urls()

    def _resolve_file(self, request, uuid):
        document = get_object_or_404(self.get_queryset(request), uuid=uuid)
        record_document_read(request.user, document, "file")
        return document, document.file, document.mime_type, document.original_filename
