from django.core.exceptions import PermissionDenied
from django.urls import path

from shared.views import stream_stored_file


def _require_view_permission(model_admin, request, instance=None):
    if not model_admin.has_view_permission(request, instance):
        raise PermissionDenied


def admin_file_path(model_admin, route, name, resolve):
    def view(request, *args, **kwargs):
        _require_view_permission(model_admin, request)
        instance, *stream_arguments = resolve(request, *args, **kwargs)
        _require_view_permission(model_admin, request, instance)
        return stream_stored_file(*stream_arguments)

    return path(route, model_admin.admin_site.admin_view(view), name=name)
