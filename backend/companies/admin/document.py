from django.contrib import admin
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from companies.models import CompanyDocument
from shared.utils.admin_files import admin_file_path


@admin.register(CompanyDocument)
class CompanyDocumentAdmin(admin.ModelAdmin):

    list_display = [
        "name",
        "company",
        "document_type",
        "is_verified",
        "created_at",
    ]
    list_filter = ["document_type", "is_verified", "created_at"]
    search_fields = ["name", "company__name"]
    readonly_fields = ["uuid", "file_link", "created_at"]

    fieldsets = [
        ("Document", {"fields": ["company", "document_type", "name"]}),
        ("File", {"fields": ["file_link", "external_url", "file_size", "mime_type"]}),
        ("Validity", {"fields": ["valid_from", "valid_until"], "classes": ["collapse"]}),
        (
            "Verification",
            {"fields": ["is_verified", "verified_at", "verified_by"], "classes": ["collapse"]},
        ),
        ("Notes", {"fields": ["notes", "rejection_reason"], "classes": ["collapse"]}),
        ("Timestamps", {"fields": ["uuid", "created_at"], "classes": ["collapse"]}),
    ]

    actions = ["verify_documents"]

    @admin.display(description="File")
    def file_link(self, obj):
        if obj.pk is None or not obj.file:
            return "-"
        url = reverse("admin:companies_companydocument_file", args=[obj.uuid])
        return format_html('<a href="{}" target="_blank">Open document</a>', url)

    def get_urls(self):
        custom_urls = [
            admin_file_path(self, "<uuid:uuid>/file/", "companies_companydocument_file", self._resolve_file),
        ]
        return custom_urls + super().get_urls()

    def _resolve_file(self, request, uuid):
        document = get_object_or_404(CompanyDocument, uuid=uuid)
        return document, document.file, document.mime_type

    @admin.action(description="Verify selected documents")
    def verify_documents(self, request, queryset):
        count = queryset.filter(is_verified=False).update(
            is_verified=True,
            verified_at=timezone.now(),
            verified_by=request.user,
        )
        self.message_user(request, f"{count} documents verified.")
