from django.urls import reverse
from django.utils.html import format_html


def document_file_link(obj):
    if obj.pk is not None and obj.file:
        url = reverse("admin:companies_companydocument_file", args=[obj.uuid])
        return format_html('<a href="{}" target="_blank">Open document</a>', url)
    if obj.external_url:
        return format_html('<a href="{}" target="_blank">External Link</a>', obj.external_url)
    return "-"
