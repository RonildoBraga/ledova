from shared.views import AuthenticatedReadOnlyViewSet
from wallets.filters import TransactionFilter
from wallets.models import Transaction
from wallets.serializers import TransactionSerializer


class TransactionViewSet(AuthenticatedReadOnlyViewSet):
    serializer_class = TransactionSerializer
    filterset_class = TransactionFilter
    ordering = ["-block_timestamp"]
    ordering_fields = ["block_timestamp", "chain"]

    def get_queryset(self):
        user = self.request.user
        return Transaction.objects.visible_to_user(user).filter(asset__is_verified=True).with_optimized_data()
