from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from companies.filters import CompanyDocumentFilter
from companies.models import Company, CompanyDocument
from companies.serializers import CompanyDocumentSerializer
from shared.views import AuthenticatedModelViewSet


class DocumentViewSet(AuthenticatedModelViewSet):
    serializer_class = CompanyDocumentSerializer
    filterset_class = CompanyDocumentFilter
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    http_method_names = ["get", "post", "delete", "head", "options"]
    ordering = ["-created_at"]
    ordering_fields = ["created_at"]

    def _writing(self):
        return self.action in ("create", "destroy")

    def _company(self):
        """The parent company from the URL, scoped like the documents themselves (writes need management rights)."""
        scope = Company.objects.manageable_by_user if self._writing() else Company.objects.visible_to_user
        company = scope(self.request.user).filter(uuid=self.kwargs["company_uuid"]).first()
        if not company:
            raise NotFound("Company not found or permission denied")
        return company

    def get_queryset(self):
        user = self.request.user
        scope = (
            CompanyDocument.objects.manageable_by_user if self._writing() else CompanyDocument.objects.visible_to_user
        )
        return scope(user).filter(company=self._company())

    def create(self, request, *args, **kwargs):
        company = self._company()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(company=company)

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()

        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
