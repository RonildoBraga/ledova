import logging
from builtins import AssertionError

from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import DatabaseError
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler

from shared.utils.logging_utils import LoggingContext

logger = logging.getLogger("ledova_backend")


def custom_exception_handler(exc, context):
    """
    Custom exception handler for DRF that provides detailed error responses
    and comprehensive logging for monitoring.

    This handler:
    - Uses DRF's default handling for APIException subclasses
    - Converts Django model exceptions to appropriate API exceptions
    - Logs all errors with relevant context
    - Returns consistent error response format

    Args:
        exc: The exception instance
        context: Dictionary with 'view' and 'request' keys

    Returns:
        Response object with error details and appropriate status code
    """
    # Get the standard error response from DRF
    response = exception_handler(exc, context)

    # If DRF didn't handle it, handle Django-specific exceptions
    if response is None:
        if isinstance(exc, ObjectDoesNotExist):
            # Convert Django's ObjectDoesNotExist to DRF's NotFound
            response = exception_handler(NotFound(str(exc)), context)
        elif isinstance(exc, Http404):
            response = Response({"error": "Not found", "detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        elif isinstance(exc, PermissionDenied):
            response = Response({"error": "Permission denied", "detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        elif isinstance(exc, DjangoValidationError):
            # Convert Django validation error to DRF validation error
            if hasattr(exc, "message_dict"):
                response = exception_handler(ValidationError(exc.message_dict), context)
            else:
                response = exception_handler(ValidationError(exc.messages), context)
        elif isinstance(exc, AssertionError):
            response = Response({"error": "Assertion error", "detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        elif isinstance(exc, DatabaseError):
            # Log database errors with full context
            logger.error(f"{LoggingContext.EXCEPTIONS} Database error: {str(exc)}", exc_info=True)
            response = Response(
                {"error": "Database error", "detail": "A database error occurred. Please try again later."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        else:
            # Unhandled exception - log with full traceback
            logger.error(f"{LoggingContext.EXCEPTIONS} Unhandled exception: {exc}", exc_info=True)
            response = Response(
                {"error": "Internal server error", "detail": "An unexpected error occurred"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # Enhance authentication error responses
    if isinstance(exc, (exceptions.AuthenticationFailed, exceptions.NotAuthenticated)):
        if response.data.get("detail"):
            response.data = {
                "error": "Authentication failed",
                "detail": response.data["detail"],
                "code": getattr(exc, "code", "authentication_failed"),
            }

    # Log all errors with context
    if response is not None:
        view = context.get("view", None)
        request = context.get("request", None)

        log_data = {
            "status_code": response.status_code,
            "error": str(exc),
            "view": view.__class__.__name__ if view else "Unknown",
            "method": request.method if request else "Unknown",
            "path": request.path if request else "Unknown",
            "user": str(request.user) if request and hasattr(request, "user") else "Anonymous",
        }

        if response.status_code >= 500:
            logger.error(f"{LoggingContext.EXCEPTIONS} Server error: {log_data}", exc_info=True)
        elif response.status_code >= 400:
            logger.warning(f"{LoggingContext.EXCEPTIONS} Client error: {log_data}")

    return response
