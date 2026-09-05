from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from operators.models import Operator
from operators.serializers import OperatorSerializer


class OperatorView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(OperatorSerializer(Operator.get()).data)
