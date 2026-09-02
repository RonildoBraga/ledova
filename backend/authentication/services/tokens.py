import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken

from authentication.models.user_token import UserToken
from shared.utils.logging_utils import LoggingContext
from shared.utils.request import extract_request_metadata

logger = logging.getLogger("ledova_backend")


class TokenService:
    @staticmethod
    @transaction.atomic
    def create(user, device_info=None, ip_address=None, user_agent=None, expires_in=None):
        try:
            refresh = RefreshToken.for_user(user)

            if not expires_in:
                expires_in = getattr(api_settings, "ACCESS_TOKEN_LIFETIME", timedelta(minutes=30))

            expires_at = timezone.now() + expires_in

            token = UserToken.objects.create(
                user=user,
                access_token=str(refresh.access_token),
                refresh_token=str(refresh),
                expires_at=expires_at,
                ip_address=ip_address,
                user_agent=user_agent,
                device_info=device_info or {},
                last_used_at=timezone.now(),
            )

            logger.info(f"{LoggingContext.TOKEN_MANAGEMENT} Token created for user {user.email}")
            return token
        except Exception as e:
            logger.error(f"{LoggingContext.TOKEN_MANAGEMENT} Token creation failed: {str(e)}", exc_info=True)
            raise

    @staticmethod
    @transaction.atomic
    def get_or_create(user, request=None):
        existing_token = UserToken.objects.get_active_token_for_user(user)
        device_info, ip_address, user_agent = extract_request_metadata(request)

        if existing_token and not existing_token.is_expired:
            existing_token.last_used_at = timezone.now()
            existing_token.ip_address = ip_address
            existing_token.user_agent = user_agent
            existing_token.device_info = device_info
            existing_token.save()
            return existing_token
        elif existing_token and existing_token.is_active and existing_token.is_expired:
            return TokenService.refresh(existing_token.refresh_token)
        else:
            return TokenService.create(user, device_info, ip_address, user_agent)

    @staticmethod
    @transaction.atomic
    def refresh(refresh_token):
        try:
            token_obj = UserToken.objects.get_by_refresh_token(refresh_token)
            if not token_obj:
                return None

            user = token_obj.user

            try:
                if getattr(api_settings, "ROTATE_REFRESH_TOKENS", False):
                    token_obj.is_active = False
                    token_obj.revoked_at = timezone.now()
                    token_obj.save(update_fields=["is_active", "revoked_at"])

                refresh = RefreshToken.for_user(user)
                access_token_lifetime = getattr(api_settings, "ACCESS_TOKEN_LIFETIME", timedelta(minutes=30))
                expires_at = timezone.now() + access_token_lifetime

                new_token = UserToken.objects.create(
                    user=user,
                    access_token=str(refresh.access_token),
                    refresh_token=str(refresh),
                    expires_at=expires_at,
                    ip_address=token_obj.ip_address,
                    user_agent=token_obj.user_agent,
                    device_info=token_obj.device_info,
                    last_used_at=timezone.now(),
                )

                logger.info(f"{LoggingContext.TOKEN_MANAGEMENT} Token refreshed for user {user.email}")
                return new_token

            except Exception as e:
                logger.error(f"{LoggingContext.TOKEN_MANAGEMENT} Token refresh failed: {str(e)}", exc_info=True)
                raise

        except Exception:
            return None

    @staticmethod
    def get_active_tokens(user):
        TokenService.cleanup_expired(user)
        return UserToken.objects.filter_by_user(user).filter_active().order_by("-created_at")

    @staticmethod
    def get_by_refresh(refresh_token):
        return UserToken.objects.get_by_refresh_token(refresh_token)

    @staticmethod
    def validate(access_token):
        try:
            token = UserToken.objects.get(access_token=access_token, is_active=True)

            if token.is_expired:
                return False, {"error": "Token is expired", "code": "token_expired"}

            token.last_used_at = timezone.now()
            token.save(update_fields=["last_used_at"])

            return True, None

        except UserToken.DoesNotExist:
            return False, {"error": "Token not found or inactive", "code": "token_not_found"}
        except Exception as e:
            logger.error(f"{LoggingContext.TOKEN_MANAGEMENT} Error validating token: {str(e)}")
            return False, {"error": "Error validating token", "code": "validation_error"}

    @staticmethod
    @transaction.atomic
    def revoke(token):
        try:
            if isinstance(token, str):
                token_obj = UserToken.objects.get(access_token=token, is_active=True)
            else:
                token_obj = token

            token_obj.revoke()
            logger.info(f"{LoggingContext.TOKEN_MANAGEMENT} Token revoked")
            return True

        except UserToken.DoesNotExist:
            return False
        except Exception as e:
            logger.error(f"{LoggingContext.TOKEN_MANAGEMENT} Error revoking token: {str(e)}", exc_info=True)
            return False

    @staticmethod
    @transaction.atomic
    def revoke_by_refresh(user, refresh_token):
        try:
            token_obj = UserToken.objects.get_by_refresh_token(refresh_token)
            if token_obj and token_obj.user == user:
                token_obj.revoke()
                logger.info(f"{LoggingContext.TOKEN_MANAGEMENT} Token revoked by refresh token")
                return True
            return False
        except Exception as e:
            logger.error(f"{LoggingContext.TOKEN_MANAGEMENT} Error revoking token by refresh: {str(e)}")
            return False

    @staticmethod
    @transaction.atomic
    def revoke_all(user):
        try:
            active_tokens = UserToken.objects.filter(user=user, is_active=True)
            count = active_tokens.update(is_active=False, revoked_at=timezone.now())

            logger.info(f"{LoggingContext.TOKEN_MANAGEMENT} Revoked {count} tokens for user {user.email}")
            return count
        except Exception as e:
            logger.error(f"{LoggingContext.TOKEN_MANAGEMENT} Error revoking all tokens: {str(e)}", exc_info=True)
            raise

    @staticmethod
    def cleanup_expired(user=None):
        """Mark expired tokens inactive; returns how many were touched."""
        query = UserToken.objects.get_expired_tokens()

        if user:
            query = query.filter_by_user(user)

        cleaned_count = query.update(is_active=False)

        if cleaned_count > 0:
            logger.debug(f"{LoggingContext.TOKEN_MANAGEMENT} Cleaned up {cleaned_count} expired tokens")

        return cleaned_count
