from documents.services.access import may_review_documents, record_document_read


class AuditsDocumentReads:
    read_kind = "document"

    def document_for_read(self, obj):
        return obj

    def has_view_permission(self, request, obj=None):
        return may_review_documents(request.user) and (obj is None or self.document_for_read(obj).content_available)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        if obj is not None:
            record_document_read(request.user, self.document_for_read(obj), self.read_kind)
        return super().render_change_form(request, context, add, change, form_url, obj)

    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context)
        context = getattr(response, "context_data", None)
        if context and "cl" in context:
            for obj in context["cl"].result_list:
                record_document_read(request.user, self.document_for_read(obj), self.read_kind)
        return response
