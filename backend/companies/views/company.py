import logging

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny, IsAdminUser
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
from companies.services import submit_application
from shared.utils.logging_utils import LoggingContext
from shared.views import AuthenticatedModelViewSet
from tokens.models import (
    CapitalIncreaseRequest,
    IssuanceStatus,
    RequestStatus,
    ShareIssuance,
    ShareToken,
)

logger = logging.getLogger(__name__)


class CompanyViewSet(AuthenticatedModelViewSet):
    administrative_actions = {"api_key", "status_update"}
    manageable_actions = {
        "destroy",
        "partial_update",
        "resubmit",
        "submit",
        "update",
        "withdraw",
    }
    public_actions = {"list", "retrieve", "by_acn"}
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
        if self.action in self.public_actions:
            return [AllowAny()]
        if self.action in self.administrative_actions:
            return [IsAdminUser()]
        return super().get_permissions()

    def get_queryset(self):
        user = self.request.user

        if self.action in self.administrative_actions:
            return Company.objects.all()
        if self.action in self.manageable_actions:
            return Company.objects.manageable_by_user(user)
        if self.action == "list":
            return Company.objects.visible_to_user(user) if user.is_authenticated else Company.objects.active()
        if self.action in self.public_actions:
            return Company.objects.readable_by_user(user)
        return Company.objects.visible_to_user(user)

    def retrieve(self, request, *args, **kwargs):
        return self._company_response(self.get_object())

    def _company_response(self, company):
        """Owners get the full record; every other caller the public listing shape."""
        if company.owner_id == self.request.user.pk:
            serializer_class = CompanyDetailSerializer
        else:
            serializer_class = CompanyListSerializer
        return Response(serializer_class(company, context=self.get_serializer_context()).data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        company = serializer.save()

        logger.info(
            f"{LoggingContext.COMPANY_REGISTRATION} User {request.user.email} registered company: {company.name}"
        )

        response_serializer = CompanyDetailSerializer(company)
        return Response(
            {
                "message": "Company registered successfully. Please complete your application and submit for review.",
                "company": response_serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )

    def perform_update(self, serializer):
        company = serializer.save()
        logger.info(f"{LoggingContext.COMPANY} User {self.request.user.email} updated company: {company.name}")

    @action(detail=False, methods=["get"], url_path="acn/(?P<acn>[^/.]+)")
    def by_acn(self, request, acn=None):
        return self._company_response(get_object_or_404(self.get_queryset(), acn=acn))

    @action(detail=True, methods=["get"])
    def stats(self, request, uuid=None):
        company = self.get_object()

        tokens = ShareToken.objects.filter(company=company)
        total_tokens = tokens.filter(status="deployed").count()

        deployed_tokens = tokens.filter(status="deployed")
        total_shareholders = (
            ShareIssuance.objects.filter(
                token__in=deployed_tokens,
                status=IssuanceStatus.COMPLETED,
            )
            .values("recipient_address")
            .distinct()
            .count()
        )

        pending_capital_increases = CapitalIncreaseRequest.objects.filter(
            token__company=company,
            status__in=[
                RequestStatus.SUBMITTED,
                RequestStatus.UNDER_REVIEW,
                RequestStatus.APPROVED,
            ],
        ).count()

        data = {
            "totalTokens": total_tokens,
            "totalShareholders": total_shareholders,
            "pendingActions": pending_capital_increases,
            "pendingCapitalIncreases": pending_capital_increases,
        }

        return Response(data, status=status.HTTP_200_OK)

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

    @action(detail=True, methods=["post"], url_path="status")
    def status_update(self, request, uuid=None):
        company = self.get_object()

        serializer = CompanyStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        new_status = serializer.validated_data["status"]
        reason = serializer.validated_data.get("reason", "")

        back_to_active = {CompanyStatus.WARNING: company.resolve_warning, CompanyStatus.SUSPENDED: company.reinstate}
        transitions = {
            CompanyStatus.REVIEW: company.start_review,
            CompanyStatus.INFO_REQUIRED: lambda: company.request_info(reason),
            CompanyStatus.APPROVED: lambda: company.approve(approved_by=request.user),
            CompanyStatus.ACTIVE: back_to_active.get(company.status, company.activate),
            CompanyStatus.REJECTED: lambda: company.reject(reason, rejected_by=request.user),
            CompanyStatus.WARNING: lambda: company.issue_warning(reason),
            CompanyStatus.SUSPENDED: lambda: company.suspend(reason),
            CompanyStatus.DELISTED: lambda: company.delist(reason),
        }
        if new_status not in transitions:
            raise InvalidStatusTransitionException(
                from_status=company.get_status_display(),
                to_status=CompanyStatus(new_status).label,
            )
        transitions[new_status]()
        logger.info(
            f"{LoggingContext.COMPANY} {request.user.email} set {company.name} to {company.get_status_display()}"
        )

        return Response(
            {
                "message": f"Company status updated to {company.get_status_display()}",
                "company": CompanyDetailSerializer(company).data,
            }
        )

    @action(detail=True, methods=["post"])
    def submit(self, request, uuid=None):
        company = self.get_object()

        serializer = ApplicationSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        submit_application(company, submitted_by=request.user)

        return Response(
            {
                "message": "Application submitted successfully. You will be notified when the review is complete.",
                "company": ApplicationStatusSerializer(company).data,
            }
        )

    @action(detail=True, methods=["post"])
    def resubmit(self, request, uuid=None):
        company = self.get_object()

        serializer = ApplicationResubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        company.resubmit()
        logger.info(f"{LoggingContext.COMPANY} Application resubmitted: {company.name}")

        return Response(
            {
                "message": "Application resubmitted successfully.",
                "company": ApplicationStatusSerializer(company).data,
            }
        )

    @action(detail=True, methods=["post"])
    def withdraw(self, request, uuid=None):
        company = self.get_object()

        serializer = ApplicationWithdrawSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        company.withdraw(reason=serializer.validated_data.get("reason") or "")
        logger.info(f"{LoggingContext.COMPANY} Application withdrawn: {company.name}")

        return Response(
            {
                "message": "Application withdrawn successfully.",
                "company": ApplicationStatusSerializer(company).data,
            }
        )

    @action(detail=True, methods=["get"], url_path="application-status")
    def application_status(self, request, uuid=None):
        company = self.get_object()
        return Response(ApplicationStatusSerializer(company).data)
