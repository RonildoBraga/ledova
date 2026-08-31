from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from users.services import IdentityVerificationService


class IdentityVerificationViewSet(ViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["post"], url_path="token")
    def token(self, request):
        user_profile = request.user.userprofile
        session = IdentityVerificationService.get_verification_session(user_profile)
        return Response(
            {
                "provider": session.provider,
                "applicantId": session.applicant_id,
                "accessToken": session.access_token,
                "formUrl": session.form_url,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"], url_path="status")
    def verification_status(self, request):
        user_profile = request.user.userprofile
        return Response(
            IdentityVerificationService.get_verification_status(user_profile),
            status=status.HTTP_200_OK,
        )
