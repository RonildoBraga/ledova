import logging
import os
from datetime import datetime

from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from authentication.managers.user import V2EmailLookupState
from authentication.models.user_token import UserToken
from authentication.serializers.user import (
    ChangePasswordSerializer,
    EmailVerificationSerializer,
    UserSigninSerializer,
    UserSignupSerializer,
    UserTokenSerializer,
)
from authentication.services.email_codes import EmailCodeService
from authentication.services.sessions import SessionService
from authentication.services.tokens import TokenService
from shared.utils.logging_utils import LoggingContext

User = get_user_model()

logger = logging.getLogger("ledova_backend")


class TokenCookieMixin:

    def set_token_cookies(self, response, access_token, refresh_token):
        access_lifetime = settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds()
        refresh_lifetime = settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()
        secure = settings.DEBUG is False
        domain = os.getenv("COOKIE_DOMAIN")
        cookie_access_name = os.getenv("COOKIE_ACCESS_NAME", "access")
        cookie_refresh_name = os.getenv("COOKIE_REFRESH_NAME", "refresh")

        response.set_cookie(
            cookie_access_name,
            access_token,
            max_age=int(access_lifetime),
            httponly=True,
            secure=secure,
            domain=domain,
            samesite="Lax",
            path="/",
        )
        response.set_cookie(
            cookie_refresh_name,
            refresh_token,
            max_age=int(refresh_lifetime),
            httponly=True,
            secure=secure,
            domain=domain,
            samesite="Lax",
            path="/",
        )
        return response

    def clear_token_cookies(self, response):
        cookie_access_name = os.getenv("COOKIE_ACCESS_NAME", "access")
        cookie_refresh_name = os.getenv("COOKIE_REFRESH_NAME", "refresh")
        domain = os.getenv("COOKIE_DOMAIN")

        response.delete_cookie(cookie_access_name, path="/", domain=domain, samesite="Lax")
        response.delete_cookie(cookie_refresh_name, path="/", domain=domain, samesite="Lax")
        return response


class AuthViewSet(TokenCookieMixin, ViewSet):
    throttle_scope = "auth"

    def get_permissions(self):
        if self.action in ["resend_verification", "change_password"]:
            return [IsAuthenticated()]
        return [AllowAny()]

    @action(detail=False, methods=["post"], url_path="signup")
    def signup(self, request):
        serializer = UserSignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]
        password_confirmation = serializer.validated_data["password_confirm"]

        user = SessionService.signup_without_token(email, password, password_confirmation)
        EmailCodeService.send(user)

        response_serializer = UserSignupSerializer(instance=user)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="signin")
    def signin(self, request):
        serializer = UserSigninSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]

        user, token = SessionService.login(email, password, request)

        response_serializer = UserSigninSerializer(instance=user)
        resp = Response(response_serializer.data, status=status.HTTP_200_OK)

        return self.set_token_cookies(resp, token.access_token, token.refresh_token)

    @action(detail=False, methods=["post"], url_path="signout")
    def signout(self, request):
        if request.user.is_authenticated:
            cookie_refresh_name = os.getenv("COOKIE_REFRESH_NAME", "refresh")
            refresh_token = request.COOKIES.get(cookie_refresh_name)
            SessionService.logout(request.user, refresh_token)

        response = Response({"message": "Successfully signed out."}, status=status.HTTP_200_OK)
        return self.clear_token_cookies(response)

    @action(detail=False, methods=["post"], url_path="token/refresh")
    def token_refresh(self, request):
        cookie_refresh_name = os.getenv("COOKIE_REFRESH_NAME", "refresh")
        refresh_token = request.COOKIES.get(cookie_refresh_name)

        if not refresh_token:
            return Response({"error": "Refresh token not found in cookies."}, status=status.HTTP_400_BAD_REQUEST)

        user_token = UserToken.objects.get_by_refresh_token(refresh_token)
        if not user_token:
            resp = Response({"error": "Invalid refresh token."}, status=status.HTTP_401_UNAUTHORIZED)
            return self.clear_token_cookies(resp)
        else:
            new_user_token = TokenService.get_or_create(user_token.user, request)
            serializer = UserTokenSerializer(instance=new_user_token)
            response = Response(serializer.data, status=status.HTTP_200_OK)
            return self.set_token_cookies(response, new_user_token.access_token, new_user_token.refresh_token)

    @action(detail=False, methods=["post"], url_path="email-verification")
    def email_verification(self, request):
        serializer = EmailVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        token = serializer.validated_data["token"]
        email = serializer.validated_data["email"]

        lookup = User.objects.resolve_v2_email(email)
        user = lookup.user if lookup.state is V2EmailLookupState.UNIQUE else None

        if user is None or not EmailCodeService.verify(user, token):
            return Response(
                {"token": ["Invalid email or verification code."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        jwt_token = TokenService.get_or_create(user, request)
        response_serializer = EmailVerificationSerializer(instance=user)
        response = Response(response_serializer.data, status=status.HTTP_200_OK)
        return self.set_token_cookies(response, jwt_token.access_token, jwt_token.refresh_token)

    @action(detail=False, methods=["post"], url_path="resend-verification")
    def resend_verification(self, request):
        user = request.user

        if user.is_email_verified:
            return Response({"message": "Email is already verified."}, status=status.HTTP_400_BAD_REQUEST)

        EmailCodeService.send(user)
        logger.info(f"{LoggingContext.EMAIL_VERIFICATION} Resent verification email to {user.email}")

        return Response({"message": "Verification email sent successfully."}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="auth/verify")
    def verify(self, request):
        if request.user.is_authenticated and request.auth:
            return Response(
                {
                    "valid": True,
                    "expiresAt": datetime.fromtimestamp(request.auth["exp"]).isoformat(),
                }
            )
        return Response({"valid": False}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="change-password")
    def change_password(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        current_password = serializer.validated_data["current_password"]
        new_password = serializer.validated_data["new_password"]

        if not user.check_password(current_password):
            return Response(
                {"current_password": ["Current password is incorrect."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(new_password)
        user.save(update_fields=["password"])

        logger.info(f"{LoggingContext.AUTH} Password changed successfully for user {user.email}")

        return Response({"message": "Password changed successfully."}, status=status.HTTP_200_OK)
