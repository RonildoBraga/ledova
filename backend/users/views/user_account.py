from shared.db import atomic
from shared.views.base import AuthenticatedModelViewSet
from users.models import UserAccount
from users.serializers.user_account import UserAccountSerializer
from users.services import register_account


class UserAccountViewSet(AuthenticatedModelViewSet):
    serializer_class = UserAccountSerializer
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    ordering = ["-activation_date"]
    ordering_fields = ["activation_date", "created_at"]

    def get_queryset(self):
        queryset = UserAccount.objects.accounts_the_user_is_a_member_of(self.request.user)
        if getattr(self, "action", None) in {"update", "partial_update"}:
            return queryset.select_for_update()
        return queryset

    def perform_create(self, serializer):
        profile = self.request.user.userprofile
        register_account(serializer.save(director=profile), profile)

    def perform_update(self, serializer):
        return serializer.save()

    @atomic()
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @atomic()
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)
