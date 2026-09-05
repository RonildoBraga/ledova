import logging

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from whitelist.constants import (
    WHITELIST_STATUS_NOT_WHITELISTED,
    WHITELIST_STATUS_UNKNOWN,
    WHITELIST_STATUS_WHITELISTED,
)
from whitelist.serializers import WhitelistStatusSerializer
from whitelist.services import WhitelistService

logger = logging.getLogger(__name__)


class WhitelistStatusView(APIView):

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
                "status": (WHITELIST_STATUS_WHITELISTED if info["whitelisted"] else WHITELIST_STATUS_NOT_WHITELISTED),
            }
        except Exception as e:
            logger.warning(f"Failed to fetch whitelist status: {e}")
            data = {
                "address": address,
                "is_whitelisted": False,
                "can_receive": False,
                "status": WHITELIST_STATUS_UNKNOWN,
            }

        serializer = WhitelistStatusSerializer(data)
        return Response(serializer.data)
