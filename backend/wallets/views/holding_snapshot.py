from shared.views import AuthenticatedReadOnlyViewSet
from wallets.filters import HoldingSnapshotFilter
from wallets.models import HoldingSnapshot
from wallets.serializers import HoldingSnapshotSerializer


class HoldingSnapshotViewSet(AuthenticatedReadOnlyViewSet):
    serializer_class = HoldingSnapshotSerializer
    filterset_class = HoldingSnapshotFilter
    ordering = ["-snapshot_date"]
    ordering_fields = ["snapshot_date", "snapshot_reason"]

    def get_queryset(self):
        user = self.request.user
        return HoldingSnapshot.objects.visible_to_user(user).with_optimized_data()
