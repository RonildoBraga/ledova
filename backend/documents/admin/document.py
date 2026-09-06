from django.contrib import admin
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.html import format_html

from documents.models import Document
from shared.utils.admin_files import admin_file_path


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("uuid", "uploaded_by", "document_type", "original_filename", "created_at")
    list_filter = ("document_type", "created_at")
    search_fields = ("uploaded_by__email", "original_filename", "note")
    readonly_fields = ("uuid", "file_link", "created_at", "updated_at")
    raw_id_fields = ("uploaded_by",)
    ordering = ("-created_at",)

    fieldsets = [
        ("Document", {"fields": ["uploaded_by", "document_type", "note"]}),
        ("File", {"fields": ["file_link", "original_filename", "mime_type"]}),
        ("Timestamps", {"fields": ["uuid", "created_at", "updated_at"], "classes": ["collapse"]}),
    ]

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
        document = get_object_or_404(Document, uuid=uuid)
        return document, document.file, document.mime_type, document.original_filename
