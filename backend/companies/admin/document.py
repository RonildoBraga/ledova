from django.contrib import admin
from django.shortcuts import get_object_or_404
from django.urls import path
from django.utils import timezone

from companies.admin._helpers import document_file_link
from companies.models import CompanyDocument
from shared.views import stream_stored_file


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
        ("Document", {"fields": ["uuid", "company", "document_type", "name"]}),
        ("Content", {"fields": ["file_link", "external_url", "file_size", "mime_type"]}),
        ("Validity", {"fields": ["valid_from", "valid_until"]}),
        ("Verification", {"fields": ["is_verified", "verified_at", "verified_by"]}),
        ("Notes", {"fields": ["notes", "rejection_reason"], "classes": ["collapse"]}),
        ("Timestamps", {"fields": ["created_at"], "classes": ["collapse"]}),
    ]

    actions = ["verify_documents"]

    @admin.display(description="File")
    def file_link(self, obj):
        return document_file_link(obj)

    def get_urls(self):
        custom_urls = [
            path(
                "<uuid:uuid>/file/",
                self.admin_site.admin_view(self.file_view),
                name="companies_companydocument_file",
            ),
        ]
        return custom_urls + super().get_urls()

    def file_view(self, request, uuid):
        document = get_object_or_404(CompanyDocument, uuid=uuid)
        return stream_stored_file(document.file, document.mime_type)

    @admin.action(description="Verify selected documents")
    def verify_documents(self, request, queryset):
        count = queryset.filter(is_verified=False).update(
            is_verified=True,
            verified_at=timezone.now(),
            verified_by=request.user,
        )
        self.message_user(request, f"{count} documents verified.")
