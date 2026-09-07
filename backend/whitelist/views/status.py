from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from shared.views.principal import SetsThePrincipalOnTheConnection
from whitelist.serializers import WhitelistStatusSerializer
from whitelist.services import WhitelistService


class WhitelistStatusView(SetsThePrincipalOnTheConnection, APIView):

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=WhitelistStatusSerializer)
    def get(self, request, address):
        data = WhitelistService().investor_status(address)

        return Response(WhitelistStatusSerializer(data).data)
