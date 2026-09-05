from datetime import datetime

from django.conf import settings
from django.contrib.auth import get_user_model
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet
from rest_framework_simplejwt.exceptions import TokenError

from authentication.classes import HybridJWTAuthentication
from authentication.managers.user import EmailLookupState
from authentication.serializers.user import (
    ChangePasswordSerializer,
    EmailVerificationSerializer,
    ResendVerificationSerializer,
    UserSigninSerializer,
    UserSignupSerializer,
)
from authentication.services.email_codes import EmailCodeService
from authentication.services.sessions import SessionService
from authentication.services.tokens import TokenService
from authentication.throttles import EmailRateThrottle

User = get_user_model()

TRANSPORT_HEADER = "X-Auth-Transport"


def bearer_transport(request):
    """`X-Auth-Transport: bearer` (the mobile app) asks for the tokens in the body and no cookies;
    without the header (the dashboard) the cookies carry the session and no body ever does."""
    return request.headers.get(TRANSPORT_HEADER, "").strip().lower() == "bearer"


class TokenCookieMixin:
    def set_token_cookies(self, response, access_token, refresh_token):
        cookie = settings.AUTH_COOKIE
        pairs = (
            (cookie["access"], access_token, settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"]),
            (cookie["refresh"], refresh_token, settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"]),
        )
        for name, value, lifetime in pairs:
            response.set_cookie(
                name,
                value,
                max_age=int(lifetime.total_seconds()),
                httponly=True,
                secure=cookie["secure"],
                domain=cookie["domain"],
                samesite=cookie["samesite"],
                path="/",
            )
        return response

    def clear_token_cookies(self, response):
        cookie = settings.AUTH_COOKIE
        for name in (cookie["access"], cookie["refresh"]):
            response.delete_cookie(name, path="/", domain=cookie["domain"], samesite=cookie["samesite"])
        return response

    def session_response(self, request, data, access_token, refresh_token):
        """A bearer body carries raw tokens (the mobile app reads `tokens[0]`), so it must never be
        cached. On the cookie transport `get_token` makes CsrfViewMiddleware send a fresh `csrftoken`
        cookie with the auth cookies."""
        bearer = bearer_transport(request)
        if bearer:
            data["tokens"] = [{"access_token": access_token, "refresh_token": refresh_token}]
        response = Response(data, status=status.HTTP_200_OK, headers={"Cache-Control": "no-store"})
        if bearer:
            return response
        get_token(request)
        return self.set_token_cookies(response, access_token, refresh_token)

    def presented_refresh_token(self, request):
        """Body first (native transport, no CSRF exposure), then the cookie, which the bearer
        transport never reads.

        A refresh cookie is sent by the browser on its own, so using it on an
        unsafe request needs the CSRF token unless a Bearer header authenticated
        the request (installed mobile builds replay the cookie beside their token).
        """
        body_token = request.data.get("refresh") if hasattr(request.data, "get") else None
        if body_token or bearer_transport(request):
            return body_token
        cookie_token = request.COOKIES.get(settings.AUTH_COOKIE["refresh"])
        if cookie_token and not HybridJWTAuthentication().get_header(request):
            HybridJWTAuthentication.enforce_csrf(request)
        return cookie_token


class AuthViewSet(TokenCookieMixin, ViewSet):
    throttle_scope = "auth"
    email_throttled_actions = ("signin", "signup", "email_verification", "resend_verification")

    def get_throttles(self):
        throttles = super().get_throttles()
        if self.action in self.email_throttled_actions:
            throttles.append(EmailRateThrottle())
        return throttles

    def get_permissions(self):
        if self.action in ["change_password", "signout_all"]:
            return [IsAuthenticated()]
        return [AllowAny()]

    @action(detail=False, methods=["post"], url_path="signup")
    def signup(self, request):
        serializer = UserSignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]
        password_confirmation = serializer.validated_data["password_confirm"]

        user = SessionService.signup(email, password, password_confirmation)
        EmailCodeService.send(user)

        response_serializer = UserSignupSerializer(instance=user)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="signin")
    def signin(self, request):
        serializer = UserSigninSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]

        user = SessionService.login(email, password)
        access_token, refresh_token = TokenService.issue(user)
        return self.session_response(request, UserSigninSerializer(instance=user).data, access_token, refresh_token)

    @action(detail=False, methods=["post"], url_path="signout")
    def signout(self, request):
        if request.user.is_authenticated:
            refresh_jti = request.auth.get("rjti") if request.auth else None
            SessionService.logout(self.presented_refresh_token(request), refresh_jti)

        response = Response({"message": "Successfully signed out."}, status=status.HTTP_200_OK)
        return self.clear_token_cookies(response)

    @action(detail=False, methods=["post"], url_path="signout-all")
    def signout_all(self, request):
        TokenService.revoke_all(request.user)

        response = Response({"message": "Successfully signed out."}, status=status.HTTP_200_OK)
        return self.clear_token_cookies(response)

    @action(detail=False, methods=["post"], url_path="token/refresh")
    def token_refresh(self, request):
        refresh_token = self.presented_refresh_token(request)
        if not refresh_token:
            return Response({"error": "Refresh token not found."}, status=status.HTTP_400_BAD_REQUEST)

        bearer = bearer_transport(request)
        try:
            _, access_token, refresh_token = TokenService.rotate(refresh_token)
        except TokenError:
            resp = Response({"error": "Invalid refresh token."}, status=status.HTTP_401_UNAUTHORIZED)
            return resp if bearer else self.clear_token_cookies(resp)

        if bearer:
            return Response(
                {"access": access_token, "refresh": refresh_token},
                status=status.HTTP_200_OK,
                headers={"Cache-Control": "no-store"},
            )
        response = Response(
            {"message": "Session refreshed."}, status=status.HTTP_200_OK, headers={"Cache-Control": "no-store"}
        )
        return self.set_token_cookies(response, access_token, refresh_token)

    @action(detail=False, methods=["post"], url_path="email-verification")
    def email_verification(self, request):
        serializer = EmailVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        token = serializer.validated_data["token"]
        email = serializer.validated_data["email"]

        lookup = User.objects.resolve_email(email)
        user = lookup.user if lookup.state is EmailLookupState.UNIQUE else None

        if user is None or not EmailCodeService.verify(user, token):
            return Response(
                {"token": ["Invalid email or verification code."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        access_token, refresh_token = TokenService.issue(user)
        return self.session_response(
            request, EmailVerificationSerializer(instance=user).data, access_token, refresh_token
        )

    @action(detail=False, methods=["post"], url_path="resend-verification")
    def resend_verification(self, request):
        """Signup issues no session, so the address comes in the body; an authenticated caller without
        one is served by its own address (the current client builds). The reply never says whether the
        address exists or is verified: signup already reveals registration and nothing more is added."""
        serializer = ResendVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data.get("email")
        if email:
            lookup = User.objects.resolve_email(email)
            user = lookup.user if lookup.state is EmailLookupState.UNIQUE else None
        elif request.user.is_authenticated:
            user = request.user
        else:
            return Response({"email": ["This field is required."]}, status=status.HTTP_400_BAD_REQUEST)

        if user is not None and not user.is_email_verified:
            EmailCodeService.send(user)

        return Response(
            {"message": "A verification code has been sent if the address needs verification."},
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"], url_path="auth/verify")
    @method_decorator(ensure_csrf_cookie)
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
        TokenService.revoke_all(user, keep_jti=request.auth.get("rjti"))

        return Response({"message": "Password changed successfully."}, status=status.HTTP_200_OK)
