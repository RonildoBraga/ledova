from shared.db import atomic
from shared.views.base import AuthenticatedModelViewSet
from users.models.financial_profile import FinancialProfile
from users.serializers.financial_profile import FinancialProfileSerializer


class FinancialProfileViewSet(AuthenticatedModelViewSet):
    serializer_class = FinancialProfileSerializer
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    ordering = ["created_at"]
    ordering_fields = ["created_at"]

    scoped_model = FinancialProfile

    def narrow(self, queryset):
        if getattr(self, "action", None) in {"update", "partial_update"}:
            return queryset.select_for_update()
        return queryset

    def perform_create(self, serializer):
        serializer.save(user_profile=self.request.user.userprofile)

    def perform_update(self, serializer):
        serializer.save()

    @atomic()
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)
