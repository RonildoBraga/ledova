from django.contrib.auth import get_user_model
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()


class TokenService:

    @staticmethod
    def issue(user):
        refresh = RefreshToken.for_user(user)
        access = refresh.access_token
        access["rjti"] = refresh["jti"]
        return str(access), str(refresh)

    @staticmethod
    def rotate(raw_refresh):
        token = RefreshToken(raw_refresh)
        user = User.objects.filter(pk=token[api_settings.USER_ID_CLAIM], is_active=True).first()
        if user is None:
            raise TokenError("User is inactive")
        token.blacklist()
        return (user, *TokenService.issue(user))

    @staticmethod
    def revoke(raw_refresh):
        try:
            RefreshToken(raw_refresh).blacklist()
        except TokenError:
            pass

    @staticmethod
    def revoke_jti(jti):
        outstanding = OutstandingToken.objects.filter(jti=jti).first()
        if outstanding is not None:
            BlacklistedToken.objects.get_or_create(token=outstanding)

    @staticmethod
    def is_session_live(jti):
        return OutstandingToken.objects.filter(jti=jti, blacklistedtoken__isnull=True).exists()

    @staticmethod
    def revoke_all(user, keep_jti=None):
        outstanding = OutstandingToken.objects.filter(user=user, blacklistedtoken__isnull=True)
        if keep_jti:
            outstanding = outstanding.exclude(jti=keep_jti)
        BlacklistedToken.objects.bulk_create([BlacklistedToken(token=token) for token in outstanding])
