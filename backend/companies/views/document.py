import logging

from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from companies.filters import CompanyDocumentFilter
from companies.models import Company, CompanyDocument
from companies.serializers import CompanyDocumentSerializer
from shared.utils.logging_utils import LoggingContext
from shared.views import AuthenticatedModelViewSet

logger = logging.getLogger(__name__)


class DocumentViewSet(AuthenticatedModelViewSet):
    serializer_class = CompanyDocumentSerializer
    filterset_class = CompanyDocumentFilter
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    http_method_names = ["get", "post", "delete", "head", "options"]
    ordering = ["-created_at"]
    ordering_fields = ["created_at"]

    def get_queryset(self):
        company_uuid = self.kwargs.get("company_uuid")
        user = self.request.user

        if self.action in ("create", "destroy"):
            qs = CompanyDocument.objects.manageable_by_user(user)
        else:
            qs = CompanyDocument.objects.visible_to_user(user)

        if company_uuid:
            company_queryset = (
                Company.objects.manageable_by_user(user)
                if self.action in ("create", "destroy")
                else Company.objects.visible_to_user(user)
            )
            company = company_queryset.filter(uuid=company_uuid).first()
            if not company:
                raise NotFound("Company not found or permission denied")
            qs = qs.filter(company=company)

        return qs

    def create(self, request, *args, **kwargs):
        company_uuid = self.kwargs.get("company_uuid")
        company = Company.objects.manageable_by_user(request.user).filter(uuid=company_uuid).first()
        if not company:
            raise NotFound("Company not found or permission denied")

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(company=company)

        logger.info(f"{LoggingContext.COMPANY_DOCUMENT} Document uploaded for company: {company.name}")

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()

        logger.info(
            f"{LoggingContext.COMPANY_DOCUMENT} Document deleted for company: "
            f"{instance.company.name} - {instance.document_type}"
        )

        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
