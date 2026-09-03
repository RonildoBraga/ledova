from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import DatabaseError
from django.http import Http404
from django.test import RequestFactory, SimpleTestCase
from rest_framework.exceptions import NotAuthenticated
from rest_framework.request import Request
from rest_framework.views import APIView

from shared.api.exceptions import custom_exception_handler


class FakeUser:
    pk = 42
    is_authenticated = True

    def __str__(self):
        return "person@example.test"


class CustomExceptionHandlerTests(SimpleTestCase):
    def handle(self, exc, user=None):
        request = Request(RequestFactory().get("/api/v1/example/"))
        if user is not None:
            request.user = user
        with self.assertLogs("shared.api.exceptions", level="WARNING") as logs:
            response = custom_exception_handler(exc, {"view": APIView(), "request": request})
        return response, "\n".join(logs.output)

    def test_object_does_not_exist_becomes_404_with_detail(self):
        response, _ = self.handle(ObjectDoesNotExist("Widget matching query does not exist."))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data, {"detail": "Widget matching query does not exist."})

    def test_django_validation_error_becomes_400(self):
        response, _ = self.handle(DjangoValidationError({"name": ["Required."]}))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"name": ["Required."]})

        response, _ = self.handle(DjangoValidationError("Bad input."))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, ["Bad input."])

    def test_django_http_exceptions_keep_drf_default_shape(self):
        response, _ = self.handle(Http404("gone"))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(list(response.data), ["detail"])

        response, _ = self.handle(PermissionDenied("nope"))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(list(response.data), ["detail"])

    def test_database_error_becomes_503(self):
        response, output = self.handle(DatabaseError("connection reset"))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.data,
            {"error": "Database error", "detail": "A database error occurred. Please try again later."},
        )
        self.assertIn("Database error", output)

    def test_assertion_error_is_an_internal_error_not_a_client_error(self):
        response, output = self.handle(AssertionError("serializer misuse"))
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.data, {"error": "Internal server error", "detail": "An unexpected error occurred"})
        self.assertIn("Unhandled exception", output)

    def test_authentication_errors_keep_error_and_code_keys(self):
        response, _ = self.handle(NotAuthenticated())
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.data,
            {
                "error": "Authentication failed",
                "detail": "Authentication credentials were not provided.",
                "code": "authentication_failed",
            },
        )

    def test_log_line_carries_user_pk_not_email(self):
        _, output = self.handle(ObjectDoesNotExist("missing"), user=FakeUser())
        self.assertIn("'user': 42", output)
        self.assertNotIn("person@example.test", output)
        self.assertIn("'view': 'APIView'", output)
        self.assertIn("'path': '/api/v1/example/'", output)

    def test_log_line_without_user_reports_none(self):
        _, output = self.handle(ObjectDoesNotExist("missing"))
        self.assertIn("'user': None", output)
