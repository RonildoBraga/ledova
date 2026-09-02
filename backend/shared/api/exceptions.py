import logging

from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import DatabaseError
from rest_framework import exceptions, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler

from shared.utils.logging_utils import LoggingContext

logger = logging.getLogger("ledova_backend")


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is None:
        if isinstance(exc, ObjectDoesNotExist):
            response = exception_handler(NotFound(str(exc)), context)
        elif isinstance(exc, DjangoValidationError):
            messages = exc.message_dict if hasattr(exc, "message_dict") else exc.messages
            response = exception_handler(ValidationError(messages), context)
        elif isinstance(exc, DatabaseError):
            logger.error(f"{LoggingContext.EXCEPTIONS} Database error: {exc}", exc_info=True)
            response = Response(
                {"error": "Database error", "detail": "A database error occurred. Please try again later."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        else:
            logger.error(f"{LoggingContext.EXCEPTIONS} Unhandled exception: {exc}", exc_info=True)
            response = Response(
                {"error": "Internal server error", "detail": "An unexpected error occurred"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    if isinstance(exc, (exceptions.AuthenticationFailed, exceptions.NotAuthenticated)) and response.data.get("detail"):
        response.data = {
            "error": "Authentication failed",
            "detail": response.data["detail"],
            "code": getattr(exc, "code", "authentication_failed"),
        }

    view = context.get("view")
    request = context.get("request")
    log_data = {
        "status_code": response.status_code,
        "error": str(exc),
        "view": view.__class__.__name__ if view else "Unknown",
        "method": request.method if request else "Unknown",
        "path": request.path if request else "Unknown",
        "user": getattr(getattr(request, "user", None), "pk", None),
    }
    if response.status_code >= 500:
        logger.error(f"{LoggingContext.EXCEPTIONS} Server error: {log_data}", exc_info=True)
    elif response.status_code >= 400:
        logger.warning(f"{LoggingContext.EXCEPTIONS} Client error: {log_data}")

    return response
