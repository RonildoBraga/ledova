"""
User session management (login/logout).

This module handles:
- User authentication (login with email/password)
- User registration (signup)
- Session logout (single device or all devices)
"""

import logging

from django.contrib.auth import authenticate, get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers

from authentication.managers.user import V2EmailLookupState
from authentication.security.v2_email import V2EmailError, normalize_v2_email
from shared.utils.logging_utils import LoggingContext

User = get_user_model()
logger = logging.getLogger("ledova_backend")


def _resolve_signup_email(email):
    try:
        destination_key = normalize_v2_email(email)
    except V2EmailError:
        raise serializers.ValidationError({"email": ["Enter a valid email address."]}) from None
    return destination_key, User.objects.resolve_v2_email(destination_key)


def _create_signup_user(email, password):
    try:
        with transaction.atomic():
            return User.objects.create_user(email=email, password=password, is_active=True)
    except (IntegrityError, ValueError):
        raise serializers.ValidationError({"email": ["Email already registered"]}) from None


class SessionService:
    """Service for managing user sessions (login/logout)."""

    @staticmethod
    def login(email, password, request=None):
        """
        Authenticate a user and create a session.

        Args:
            email: User's email address
            password: User's password
            request: HTTP request object for token generation

        Returns:
            tuple: (user, token) if successful

        Raises:
            serializers.ValidationError: For authentication failures
        """
        if not email or not password:
            raise serializers.ValidationError({"error": ["Email and password are required."]})

        user = authenticate(username=email, password=password)
        if not user:
            raise serializers.ValidationError({"error": ["Invalid email or password."]})

        if not user.is_active:
            raise serializers.ValidationError({"error": ["User account is disabled."]})

        if not hasattr(user, "userprofile") or not user.userprofile.is_signup_completed:
            raise serializers.ValidationError({"error": ["Please complete your signup before signing in."]})

        # Update last login timestamp
        user.last_login = timezone.now()
        user.save(update_fields=["last_login"])

        # Create token using TokenService
        from authentication.services.tokens import TokenService

        token = TokenService.get_or_create(user, request)

        logger.info(f"{LoggingContext.AUTH} User {user.email} successfully authenticated")
        return user, token

    @staticmethod
    @transaction.atomic
    def signup(email, password, password_confirmation, request=None):
        """
        Create a new user account and session.

        Args:
            email: User's email address
            password: User's password
            password_confirmation: Password confirmation for validation
            request: HTTP request object for token generation

        Returns:
            tuple: (user, token) if successful

        Raises:
            serializers.ValidationError: For validation failures
        """
        if not email or not password:
            raise serializers.ValidationError({"error": ["Email and password are required."]})

        if password != password_confirmation:
            raise serializers.ValidationError({"password": ["Passwords do not match."]})

        email, lookup = _resolve_signup_email(email)
        if lookup.state is V2EmailLookupState.AMBIGUOUS:
            raise serializers.ValidationError({"email": ["Email already registered"]})
        existing_user = lookup.user
        if existing_user and hasattr(existing_user, "userprofile") and existing_user.userprofile.is_signup_completed:
            raise serializers.ValidationError({"email": ["Email already registered"]})

        if existing_user:
            user = existing_user
            user.set_password(password)
            user.is_active = True
            user.save(update_fields=["password", "is_active"])
        else:
            user = _create_signup_user(email, password)

        # Create token using TokenService
        from authentication.services.tokens import TokenService

        token = TokenService.get_or_create(user, request)

        logger.info(f"{LoggingContext.USER_SIGNUP} User account created/updated for {user.email}")
        return user, token

    @staticmethod
    @transaction.atomic
    def signup_without_token(email, password, password_confirmation):
        """
        Create a new user account without issuing tokens.
        Used during signup before email verification.

        Args:
            email: User's email address
            password: User's password
            password_confirmation: Password confirmation for validation

        Returns:
            user: Created user instance

        Raises:
            serializers.ValidationError: For validation failures
        """
        if not email or not password:
            raise serializers.ValidationError({"error": ["Email and password are required."]})

        if password != password_confirmation:
            raise serializers.ValidationError({"password": ["Passwords do not match."]})

        email, lookup = _resolve_signup_email(email)
        if lookup.state is V2EmailLookupState.AMBIGUOUS:
            raise serializers.ValidationError({"email": ["Email already registered"]})
        existing_user = lookup.user
        if existing_user and hasattr(existing_user, "userprofile") and existing_user.userprofile.is_signup_completed:
            raise serializers.ValidationError({"email": ["Email already registered"]})

        if existing_user:
            user = existing_user
            user.set_password(password)
            user.is_active = True
            user.save(update_fields=["password", "is_active"])
        else:
            user = _create_signup_user(email, password)

        # Initialize user defaults (account, portfolio, preferences)
        from users.services.setup import UserSetupService

        UserSetupService.ensure_defaults(user)

        logger.info(f"{LoggingContext.USER_SIGNUP} User account created/updated for {user.email}")
        return user

    @staticmethod
    @transaction.atomic
    def logout(user, refresh_token=None):
        """
        End a user session by invalidating tokens.

        Args:
            user: The user to sign out
            refresh_token: Optional refresh token to specifically invalidate

        Returns:
            bool: True if tokens were successfully invalidated
        """
        from authentication.services.tokens import TokenService

        try:
            if refresh_token:
                success = TokenService.revoke_by_refresh(user, refresh_token)
                if success:
                    logger.info(
                        f"{LoggingContext.TOKEN_MANAGEMENT} Session ended for user {user.email} using refresh token"
                    )
                return success
            else:
                count = TokenService.revoke_all(user)
                logger.info(f"{LoggingContext.TOKEN_MANAGEMENT} Ended {count} sessions for user {user.email}")
                return count > 0

        except Exception as e:
            logger.error(
                f"{LoggingContext.TOKEN_MANAGEMENT} Logout error for user {user.email}: {str(e)}", exc_info=True
            )
            return False

    @staticmethod
    @transaction.atomic
    def logout_all(user):
        """
        End all active sessions for a user (security feature).

        Args:
            user: The user to sign out from all devices

        Returns:
            int: Number of sessions that were ended
        """
        from authentication.services.tokens import TokenService

        try:
            count = TokenService.revoke_all(user)
            logger.info(f"{LoggingContext.TOKEN_MANAGEMENT} Signed out user {user.email} from all {count} sessions")
            return count
        except Exception as e:
            logger.error(
                f"{LoggingContext.TOKEN_MANAGEMENT} Error signing out all sessions for user {user.email}: {str(e)}",
                exc_info=True,
            )
            return 0
