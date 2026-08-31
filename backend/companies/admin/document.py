from django.contrib import admin
from django.utils import timezone

from companies.models import CompanyDocument


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
    readonly_fields = ["uuid", "created_at"]

    actions = ["verify_documents"]

    @admin.action(description="Verify selected documents")
    def verify_documents(self, request, queryset):
        count = queryset.filter(is_verified=False).update(
            is_verified=True,
            verified_at=timezone.now(),
        )
        self.message_user(request, f"{count} documents verified.")
