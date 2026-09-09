from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from companies.exceptions import InvalidStatusTransitionException
from companies.filters import CompanyFilter
from companies.models import Company, CompanyStatus
from companies.serializers import (
    ApplicationResubmitSerializer,
    ApplicationStatusSerializer,
    ApplicationSubmitSerializer,
    ApplicationWithdrawSerializer,
    CompanyAPIKeySerializer,
    CompanyDetailSerializer,
    CompanyListSerializer,
    CompanyRegistrationSerializer,
    CompanyStatusUpdateSerializer,
    CompanyUpdateSerializer,
)
from companies.services import delete_company, submit_application, transition_company
from shared.views import AuthenticatedModelViewSet
from tokens.services.company_stats import company_stats


class CompanyViewSet(AuthenticatedModelViewSet):
    administrative_actions = frozenset({"api_key", "status_update"})
    operator_actions = administrative_actions
    manageable_actions = {
        "destroy",
        "partial_update",
        "resubmit",
        "submit",
        "update",
        "withdraw",
    }
    filterset_class = CompanyFilter
    ordering = ["-created_at"]
    ordering_fields = ["created_at", "name", "status"]

    def get_serializer_class(self):
        if self.action == "create":
            return CompanyRegistrationSerializer
        if self.action == "list":
            return CompanyListSerializer
        if self.action in ["update", "partial_update"]:
            return CompanyUpdateSerializer
        if self.action == "api_key":
            return CompanyAPIKeySerializer
        if self.action == "status_update":
            return CompanyStatusUpdateSerializer
        if self.action in ["submit", "application_status"]:
            return ApplicationStatusSerializer
        if self.action == "resubmit":
            return ApplicationResubmitSerializer
        if self.action == "withdraw":
            return ApplicationWithdrawSerializer
        return CompanyDetailSerializer

    def get_permissions(self):
        if self.action in self.administrative_actions:
            return [IsAdminUser()]
        return super().get_permissions()

    def get_queryset(self):
        user = self.request.user

        if self.action in self.administrative_actions:
            return Company.objects.all()
        if self.action in self.manageable_actions:
            return Company.objects.manageable_by_user(user)
        return Company.objects.visible_to_user(user)

    @extend_schema(
        responses=inline_serializer(
            name="CompanyRegistered",
            fields={"message": serializers.CharField(), "company": CompanyDetailSerializer()},
        )
    )
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        company = serializer.save()

        response_serializer = CompanyDetailSerializer(company)
        return Response(
            {
                "message": "Company registered successfully. Please complete your application and submit for review.",
                "company": response_serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )

    def perform_update(self, serializer):
        serializer.save()

    def perform_destroy(self, instance):
        delete_company(instance)

    @action(detail=True, methods=["get"])
    def stats(self, request, uuid=None):
        return Response(company_stats(self.get_object()))

    @extend_schema(responses=CompanyAPIKeySerializer)
    @action(detail=True, methods=["get", "post"], url_path="api-key")
    def api_key(self, request, uuid=None):
        company = self.get_object()

        if request.method == "GET":
            serializer = CompanyAPIKeySerializer(company)
            return Response(serializer.data)

        company.regenerate_api_key()
        serializer = CompanyAPIKeySerializer(company)
        return Response(
            {
                "message": "API key regenerated successfully",
                **serializer.data,
            }
        )

    @extend_schema(
        responses=inline_serializer(
            name="CompanyStatusUpdated",
            fields={"message": serializers.CharField(), "company": CompanyDetailSerializer()},
        )
    )
    @action(detail=True, methods=["post"], url_path="status")
    def status_update(self, request, uuid=None):
        company = self.get_object()

        serializer = CompanyStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        new_status = serializer.validated_data["status"]
        reason = serializer.validated_data.get("reason", "")

        transitions = {
            CompanyStatus.REVIEW: ("start_review", {}),
            CompanyStatus.INFO_REQUIRED: ("request_info", {"reason": reason}),
            CompanyStatus.APPROVED: ("approve", {"approved_by": request.user}),
            CompanyStatus.ACTIVE: ("set_active", {}),
            CompanyStatus.REJECTED: ("reject", {"reason": reason, "rejected_by": request.user}),
            CompanyStatus.WARNING: ("issue_warning", {"reason": reason}),
            CompanyStatus.SUSPENDED: ("suspend", {"reason": reason}),
            CompanyStatus.DELISTED: ("delist", {"reason": reason}),
        }
        if new_status not in transitions:
            raise InvalidStatusTransitionException(
                from_status=company.get_status_display(),
                to_status=CompanyStatus(new_status).label,
            )
        method, kwargs = transitions[new_status]
        declaration = {
            key: serializer.validated_data[key]
            for key in ("declarant_name", "board_resolution_reference", "attest_officeholder")
            if key in serializer.validated_data
        }
        company = transition_company(company, method, actor=request.user, declaration=declaration, **kwargs)

        return Response(
            {
                "message": f"Company status updated to {company.get_status_display()}",
                "company": CompanyDetailSerializer(company).data,
            }
        )

    @extend_schema(
        responses=inline_serializer(
            name="CompanyApplicationSubmitted",
            fields={"message": serializers.CharField(), "company": ApplicationStatusSerializer()},
        )
    )
    @action(detail=True, methods=["post"])
    def submit(self, request, uuid=None):
        company = self.get_object()

        serializer = ApplicationSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        company = submit_application(company, submitted_by=request.user)

        return Response(
            {
                "message": "Application submitted successfully. You will be notified when the review is complete.",
                "company": ApplicationStatusSerializer(company).data,
            }
        )

    @extend_schema(
        responses=inline_serializer(
            name="CompanyApplicationResubmitted",
            fields={"message": serializers.CharField(), "company": ApplicationStatusSerializer()},
        )
    )
    @action(detail=True, methods=["post"])
    def resubmit(self, request, uuid=None):
        company = self.get_object()

        serializer = ApplicationResubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        company = transition_company(company, "resubmit", response=serializer.validated_data["response"])

        return Response(
            {
                "message": "Application resubmitted successfully.",
                "company": ApplicationStatusSerializer(company).data,
            }
        )

    @extend_schema(
        responses=inline_serializer(
            name="CompanyApplicationWithdrawn",
            fields={"message": serializers.CharField(), "company": ApplicationStatusSerializer()},
        )
    )
    @action(detail=True, methods=["post"])
    def withdraw(self, request, uuid=None):
        company = self.get_object()

        serializer = ApplicationWithdrawSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        company = transition_company(company, "withdraw", reason=serializer.validated_data.get("reason") or "")

        return Response(
            {
                "message": "Application withdrawn successfully.",
                "company": ApplicationStatusSerializer(company).data,
            }
        )

    @extend_schema(responses=ApplicationStatusSerializer)
    @action(detail=True, methods=["get"], url_path="application-status")
    def application_status(self, request, uuid=None):
        company = self.get_object()
        return Response(ApplicationStatusSerializer(company).data)
