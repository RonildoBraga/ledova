import re

from django.urls import get_resolver
from django.urls.resolvers import URLPattern, URLResolver

PARAMETER = re.compile(r"\(\?P<[^>]+>[^)]*\)")
IGNORED_PREFIXES = ("/admin", "/static", "/media", "/api-auth", "/health")
BODYLESS = {"head", "options", "trace"}
PROVIDER_EXCLUSIONS = {
    ("post", "/webhooks/alchemy/"),
    ("post", "/webhooks/kycaid/"),
    ("post", "/webhooks/kycaid/crypto/"),
    ("post", "/webhooks/sumsub/"),
}
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def _walk(patterns, prefix=""):
    for entry in patterns:
        raw = str(entry.pattern)
        if isinstance(entry, URLResolver):
            yield from _walk(entry.url_patterns, prefix + raw)
        elif isinstance(entry, URLPattern):
            yield prefix + raw, entry.callback


def _normalise(path):
    path = PARAMETER.sub("{}", path)
    path = path.replace("^", "").replace("$", "").replace("\\.", ".")
    path = re.sub(r"<[^:>]+:[^>]+>", "{}", path)
    path = re.sub(r"<[^>]+>", "{}", path)
    path = "/" + path.lstrip("/")
    return path if path.endswith("/") else path + "/"


def _methods(callback):
    view = getattr(callback, "cls", None) or getattr(callback, "view_class", None)
    allowed = set(getattr(view, "http_method_names", []) or []) if view else set()
    actions = getattr(callback, "actions", None)
    if actions:
        methods = (set(actions) & allowed) if allowed else set(actions)
    elif view:
        methods = {name for name in allowed if hasattr(view, name)}
    else:
        methods = {"get"}
    return methods - BODYLESS


def registered_routes():
    routes = set()
    for path, callback in _walk(get_resolver().url_patterns):
        normalised = _normalise(path)
        if normalised.startswith(IGNORED_PREFIXES) or ".{}" in normalised:
            continue
        view = getattr(callback, "cls", None)
        if getattr(view, "__name__", "") == "APIRootView":
            continue
        for method in _methods(callback):
            routes.add((method, normalised))
    return routes


def schema_routes(document):
    return {
        (method, re.sub(r"\{[^}]+\}", "{}", path).rstrip("/") + "/")
        for path, operations in document.get("paths", {}).items()
        for method in operations
        if method in HTTP_METHODS
    }


def schema_route_drift(document, registered=None, excluded=PROVIDER_EXCLUSIONS):
    registered = registered_routes() if registered is None else registered
    declared = schema_routes(document)
    findings = []
    for method, path in sorted(registered - excluded - declared):
        findings.append(f"{method.upper()} {path}: registered operation is absent from the schema")
    for method, path in sorted(declared - registered):
        findings.append(f"{method.upper()} {path}: schema operation has no registered route")
    for method, path in sorted(excluded - registered):
        findings.append(f"{method.upper()} {path}: provider exclusion outlives its route")
    for method, path in sorted(excluded & declared):
        findings.append(f"{method.upper()} {path}: deliberately excluded provider webhook is exposed in the schema")
    return findings
