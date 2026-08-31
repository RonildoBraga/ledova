from django.contrib import admin

from documents.models import Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("uuid", "uploaded_by", "document_type", "original_filename", "created_at")
    list_filter = ("document_type", "created_at")
    search_fields = ("uploaded_by__email", "original_filename", "note")
    readonly_fields = ("uuid", "created_at", "updated_at")
    raw_id_fields = ("uploaded_by",)
    ordering = ("-created_at",)
