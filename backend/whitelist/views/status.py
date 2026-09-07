from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from whitelist.serializers import WhitelistStatusSerializer
from whitelist.services import WhitelistService


class WhitelistStatusView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, address):
        data = WhitelistService().investor_status(address)

        return Response(WhitelistStatusSerializer(data).data)
