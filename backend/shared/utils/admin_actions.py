from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.urls import path, re_path


def _require_change_permission(model_admin, request, instance=None):
    if not model_admin.has_change_permission(request, instance):
        raise PermissionDenied


def _guarded(model_admin, view, queryset):
    rows = queryset or model_admin.get_queryset

    def guarded(request, uuid, **kwargs):
        _require_change_permission(model_admin, request)
        instance = get_object_or_404(rows(request), uuid=uuid)
        _require_change_permission(model_admin, request, instance)
        return view(request, instance, **kwargs)

    return model_admin.admin_site.admin_view(guarded)


def admin_action_path(model_admin, route, name, view, queryset=None):
    return path(route, _guarded(model_admin, view, queryset), name=name)


def admin_action_re_path(model_admin, regex, name, view, queryset=None):
    return re_path(regex, _guarded(model_admin, view, queryset), name=name)
