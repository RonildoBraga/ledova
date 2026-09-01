import logging

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from whitelist.serializers import WhitelistStatusSerializer
from whitelist.services import WhitelistService

logger = logging.getLogger(__name__)


class WhitelistStatusView(APIView):
    """Return bounded eligibility for a sender-owned wallet or transfer recipient."""

    permission_classes = [IsAuthenticated]

    def get(self, request, address):
        service = WhitelistService()

        try:
            info = service.get_investor_info(address)
            can_receive = service.can_receive(address)

            data = {
                "address": service.chain_client.to_checksum_address(address),
                "is_whitelisted": info["whitelisted"],
                "can_receive": can_receive,
            }
        except Exception as e:
            logger.warning(f"Failed to fetch whitelist status: {e}")
            data = {
                "address": address,
                "is_whitelisted": False,
                "can_receive": False,
            }

        serializer = WhitelistStatusSerializer(data)
        return Response(serializer.data)
