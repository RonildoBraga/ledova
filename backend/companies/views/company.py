import logging

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response

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
from companies.services import CompanyService
from shared.utils.logging_utils import LoggingContext
from shared.views import AuthenticatedModelViewSet
from tokens.models import (
    CapitalIncreaseRequest,
    CapitalIncreaseStatus,
    IssuanceStatus,
    ShareIssuance,
    ShareToken,
)
from whitelist.models import WhitelistEntry

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
    filterset_class = CompanyFilter
    ordering = ["-created_at"]
    ordering_fields = ["created_at", "name", "status"]

    def get_serializer_class(self):
        if self.action == "create":
            return CompanyRegistrationSerializer
        if self.action == "list" or (self.action in ("retrieve", "by_acn") and not self.request.user.is_authenticated):
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
        if self.action in ["list", "retrieve", "by_acn"]:
            return [AllowAny()]
        if self.action in ["api_key", "status_update"]:
            return [IsAdminUser()]
        return super().get_permissions()

    def get_queryset(self):
        user = self.request.user

        if self.action in self.administrative_actions:
            if user.is_authenticated and user.is_staff:
                return Company.objects.all()
            return Company.objects.none()

        if self.action in self.manageable_actions:
            if user.is_authenticated:
                return Company.objects.manageable_by_user(user)
            return Company.objects.none()

        if user.is_authenticated:
            return Company.objects.visible_to_user(user)
        return Company.objects.active()

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
        user = request.user

        if user.is_authenticated:
            queryset = Company.objects.visible_to_user(user).active()
        else:
            queryset = Company.objects.active()

        try:
            company = queryset.get(acn=acn)
        except Company.DoesNotExist:
            return Response(
                {"error": "Company not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.get_serializer(company)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def stats(self, request, uuid=None):
        company = self.get_object()

        total_whitelisted = WhitelistEntry.objects.on_chain().count()

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
                CapitalIncreaseStatus.SUBMITTED,
                CapitalIncreaseStatus.UNDER_REVIEW,
                CapitalIncreaseStatus.APPROVED,
            ],
        ).count()

        data = {
            "totalWhitelisted": total_whitelisted,
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

        serializer = CompanyStatusUpdateSerializer(
            data=request.data,
            context={"instance": company},
        )
        serializer.is_valid(raise_exception=True)

        new_status = serializer.validated_data["status"]
        reason = serializer.validated_data.get("reason", "")

        if new_status == CompanyStatus.REVIEW:
            company = CompanyService.start_review(company, reviewer=request.user)
        elif new_status == CompanyStatus.INFO_REQUIRED:
            company = CompanyService.request_info(company, reason=reason, requested_by=request.user)
        elif new_status == CompanyStatus.APPROVED:
            company = CompanyService.approve_company(company, approved_by=request.user)
        elif new_status == CompanyStatus.ACTIVE:
            company = CompanyService.activate_company(company)
        elif new_status == CompanyStatus.REJECTED:
            company = CompanyService.reject_company(company, reason=reason, rejected_by=request.user)
        elif new_status == CompanyStatus.SUSPENDED:
            company = CompanyService.suspend_company(company, reason=reason, suspended_by=request.user)
        elif new_status == CompanyStatus.WARNING:
            company = CompanyService.issue_warning(company, reason=reason, issued_by=request.user)
        elif new_status == CompanyStatus.DELISTED:
            company = CompanyService.delist_company(company, reason=reason, delisted_by=request.user)

        return Response(
            {
                "message": f"Company status updated to {company.get_status_display()}",
                "company": CompanyDetailSerializer(company).data,
            }
        )

    @action(detail=True, methods=["post"])
    def submit(self, request, uuid=None):
        company = self.get_object()

        serializer = ApplicationSubmitSerializer(
            data=request.data,
            context={"company": company},
        )
        serializer.is_valid(raise_exception=True)

        company = CompanyService.submit_application(company, submitted_by=request.user)

        return Response(
            {
                "message": "Application submitted successfully. You will be notified when the review is complete.",
                "company": ApplicationStatusSerializer(company).data,
            }
        )

    @action(detail=True, methods=["post"])
    def resubmit(self, request, uuid=None):
        company = self.get_object()

        serializer = ApplicationResubmitSerializer(
            data=request.data,
            context={"company": company},
        )
        serializer.is_valid(raise_exception=True)

        response = serializer.validated_data["response"]
        company = CompanyService.resubmit_application(company, response=response)

        return Response(
            {
                "message": "Application resubmitted successfully.",
                "company": ApplicationStatusSerializer(company).data,
            }
        )

    @action(detail=True, methods=["post"])
    def withdraw(self, request, uuid=None):
        company = self.get_object()

        serializer = ApplicationWithdrawSerializer(
            data=request.data,
            context={"company": company},
        )
        serializer.is_valid(raise_exception=True)

        reason = serializer.validated_data.get("reason")
        company = CompanyService.withdraw_application(company, reason=reason)

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
