from django.contrib import admin

from documents.models import DocumentRead
from documents.services.access import may_review_documents


@admin.register(DocumentRead)
class DocumentReadAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor_id", "document_uuid", "classification_uuid", "kind")
    readonly_fields = ("uuid", "created_at", "updated_at", "actor_id", "document_uuid", "classification_uuid", "kind")
    list_filter = ("kind", "created_at")
    search_fields = ("document_uuid", "classification_uuid")

    def has_view_permission(self, request, obj=None):
        return may_review_documents(request.user) and request.user.has_perm("documents.view_documentread")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
