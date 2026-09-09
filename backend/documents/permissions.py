from rest_framework.permissions import BasePermission

from documents.services.access import documents_enabled


class DocumentsEnabled(BasePermission):
    message = "Supporting payslips are unavailable in this deployment."

    def has_permission(self, request, view):
        return documents_enabled()
