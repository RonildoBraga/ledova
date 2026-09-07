from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.urls import path, re_path


def _require_change_permission(model_admin, request, instance=None):
    if not model_admin.has_change_permission(request, instance):
        raise PermissionDenied


def _guarded(model_admin, view, rows):
    resolve = model_admin.get_queryset if rows is None else rows

    def guarded(request, uuid, **kwargs):
        _require_change_permission(model_admin, request)
        instance = get_object_or_404(resolve(request), uuid=uuid)
        _require_change_permission(model_admin, request, instance)
        return view(request, instance, **kwargs)

    return model_admin.admin_site.admin_view(guarded)


def admin_action_path(model_admin, route, name, view, rows=None):
    return path(route, _guarded(model_admin, view, rows), name=name)


def admin_action_re_path(model_admin, regex, name, view, rows=None):
    return re_path(regex, _guarded(model_admin, view, rows), name=name)
