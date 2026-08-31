from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from users.serializers import WaitlistCreateSerializer


@api_view(["POST"])
@permission_classes([AllowAny])
def waitlist_signup(request):
    serializer = WaitlistCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    waitlist_entry = serializer.save()
    return Response(
        {"success": True, "message": "Successfully added to waitlist", "data": {"email": waitlist_entry.email}},
        status=status.HTTP_201_CREATED,
    )
