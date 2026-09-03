import logging

from django.contrib.auth import authenticate, get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers

from authentication.email import EmailError, normalize_email
from authentication.managers.user import EmailLookupState
from authentication.services.tokens import TokenService
from shared.utils.logging_utils import LoggingContext

User = get_user_model()
logger = logging.getLogger("ledova_backend")


def _resolve_signup_email(email):
    try:
        destination_key = normalize_email(email)
    except EmailError:
        raise serializers.ValidationError({"email": ["Enter a valid email address."]}) from None
    return destination_key, User.objects.resolve_email(destination_key)


def _create_signup_user(email, password):
    try:
        with transaction.atomic():
            return User.objects.create_user(email=email, password=password, is_active=True)
    except (IntegrityError, ValueError):
        raise serializers.ValidationError({"email": ["Email already registered"]}) from None


class SessionService:
    @staticmethod
    def login(email, password):
        if not email or not password:
            raise serializers.ValidationError({"error": ["Email and password are required."]})

        user = authenticate(username=email, password=password)
        if not user:
            raise serializers.ValidationError({"error": ["Invalid email or password."]})

        if not user.is_active:
            raise serializers.ValidationError({"error": ["User account is disabled."]})

        if not hasattr(user, "userprofile") or not user.userprofile.is_signup_completed:
            raise serializers.ValidationError({"error": ["Please complete your signup before signing in."]})

        user.last_login = timezone.now()
        user.save(update_fields=["last_login"])

        logger.info(f"{LoggingContext.AUTH} User {user.email} successfully authenticated")
        return user

    @staticmethod
    @transaction.atomic
    def signup(email, password, password_confirmation):
        """Create the user without issuing tokens; tokens are issued after email verification.

        A repeated signup for an incomplete account never touches the stored row: knowing the
        address is not proof of ownership, so the caller only gets the verification code resent."""
        if not email or not password:
            raise serializers.ValidationError({"error": ["Email and password are required."]})

        if password != password_confirmation:
            raise serializers.ValidationError({"password": ["Passwords do not match."]})

        email, lookup = _resolve_signup_email(email)
        if lookup.state is EmailLookupState.AMBIGUOUS:
            raise serializers.ValidationError({"email": ["Email already registered"]})
        existing_user = lookup.user
        if existing_user and hasattr(existing_user, "userprofile") and existing_user.userprofile.is_signup_completed:
            raise serializers.ValidationError({"email": ["Email already registered"]})

        user = existing_user or _create_signup_user(email, password)

        from users.services.setup import ensure_defaults

        ensure_defaults(user)

        logger.info(f"{LoggingContext.USER_SIGNUP} User account created/updated for {user.email}")
        return user

    @staticmethod
    def logout(refresh_token=None, refresh_jti=None):
        """End one session: the presented refresh token, else the session the access token belongs to."""
        if refresh_token:
            TokenService.revoke(refresh_token)
        elif refresh_jti:
            TokenService.revoke_jti(refresh_jti)
