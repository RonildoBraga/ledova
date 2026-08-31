"""
Custom middleware for the Ledova application.
"""

import logging

from django.http import HttpResponse

logger = logging.getLogger("ledova_backend")


class HealthCheckMiddleware:
    """Answer /health/ without triggering Django's ALLOWED_HOSTS check.

    Load balancers (GCP HTTPS LB, Cloud Run) probe /health/ using whatever
    Host header they use internally, which changes across revisions. We reply
    before ALLOWED_HOSTS validation runs instead of weakening the allowlist.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Intercept health check requests before any other processing.
        # HEAD is accepted alongside GET so external monitors that probe with
        # HEAD (a common bandwidth-saving default) don't fall through to
        # Django's URL router and get a confusing 404.
        if request.path == "/health/" and request.method in ("GET", "HEAD"):
            return HttpResponse("OK", status=200)

        return self.get_response(request)
