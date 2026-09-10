from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from shared.views.principal import SetsThePrincipalOnTheConnection
from users.models import UserProfile
from users.services import IdentityVerificationService


class IdentityVerificationViewSet(SetsThePrincipalOnTheConnection, ViewSet):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=None,
        responses=inline_serializer(
            name="IdentityVerificationSession",
            fields={
                "provider": serializers.CharField(),
                "applicantId": serializers.CharField(allow_null=True),
                "accessToken": serializers.CharField(allow_null=True),
                "formUrl": serializers.CharField(allow_null=True),
            },
        ),
    )
    @action(detail=False, methods=["post"], url_path="token")
    def token(self, request):
        user_profile = get_object_or_404(UserProfile, user=request.user)
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

    @extend_schema(
        responses=inline_serializer(
            name="IdentityVerificationStatus",
            fields={
                "provider": serializers.CharField(),
                "applicantId": serializers.CharField(allow_null=True),
                "status": serializers.CharField(allow_null=True),
                "reviewResult": serializers.CharField(allow_null=True),
                "reviewAnswer": serializers.CharField(allow_null=True),
                "isVerified": serializers.BooleanField(),
                "verifiedAt": serializers.DateTimeField(allow_null=True),
                "rejectionLabels": serializers.ListField(child=serializers.CharField()),
                "needsRetry": serializers.BooleanField(),
                "extractedData": serializers.JSONField(allow_null=True),
            },
        )
    )
    @action(detail=False, methods=["get"], url_path="status")
    def verification_status(self, request):
        user_profile = get_object_or_404(UserProfile, user=request.user)
        return Response(
            IdentityVerificationService.get_verification_status(user_profile),
            status=status.HTTP_200_OK,
        )
