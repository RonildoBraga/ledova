import logging

from django.db import transaction

from shared.utils.logging_utils import LoggingContext
from users.exceptions import (
    InvalidUserAccountOperationException,
    UserAccountNotFoundException,
)
from users.models import UserAccount, UserProfile

logger = logging.getLogger("ledova_backend")


class UserAccountService:

    @staticmethod
    @transaction.atomic
    def create_customer_account(account_data, user_profiles, director_id=None):
        account = UserAccount.objects.create(**account_data)

        # Associate user profiles with the account
        for profile in user_profiles:
            account.user_profiles.add(profile)

        # Set director if specified and validate
        if director_id:
            try:
                director = UserProfile.objects.get(pk=director_id)
                if director not in user_profiles:
                    raise InvalidUserAccountOperationException("Director must be one of the associated user profiles")
                account.director = director
                account.save(update_fields=["director"])
            except UserProfile.DoesNotExist:
                raise UserAccountNotFoundException(account_type=f"Director with ID {director_id}")
        # For individual accounts with single user, set as director
        elif account.account_type == "individual" and len(user_profiles) == 1:
            account.director = user_profiles[0]
            account.save(update_fields=["director"])

        return account

    @staticmethod
    @transaction.atomic
    def process_director_for_individual_account(account_id):
        try:
            account = UserAccount.objects.get(pk=account_id)

            if account.account_type == "individual" and not account.director:
                user_profiles = account.user_profiles.all()
                if user_profiles.count() == 1:
                    # Update the director field only
                    UserAccount.objects.filter(pk=account.pk).update(director=user_profiles.first())
                    return True
            return False
        except UserAccount.DoesNotExist:
            logger.error(f"{LoggingContext.ACCOUNTS} Customer Account with ID {account_id} not found")
            return False

    @staticmethod
    @transaction.atomic
    def assign_director(account_id, director_profile_id):
        try:
            account = UserAccount.objects.get(pk=account_id)
            director = UserProfile.objects.get(pk=director_profile_id)

            # Validate director is associated with the account
            if director not in account.user_profiles.all():
                raise InvalidUserAccountOperationException(
                    "Director must be one of the user profiles associated with this account"
                )

            # Set director
            account.director = director
            account.save(update_fields=["director"])

            return True
        except UserAccount.DoesNotExist:
            logger.error(f"{LoggingContext.ACCOUNTS} Customer Account with ID {account_id} not found")
            return False
        except UserProfile.DoesNotExist:
            logger.error(f"{LoggingContext.ACCOUNTS} UserProfile with ID {director_profile_id} not found")
            return False

    @staticmethod
    @transaction.atomic
    def add_user_profile_to_account(account_id, user_profile_id):
        try:
            account = UserAccount.objects.get(pk=account_id)
            profile = UserProfile.objects.get(pk=user_profile_id)

            if profile not in account.user_profiles.all():
                account.user_profiles.add(profile)

                # If this is the first profile for an individual account, set as director
                if account.account_type == "individual" and not account.director:
                    if account.user_profiles.count() == 1:
                        account.director = profile
                        account.save(update_fields=["director"])

            return True
        except UserAccount.DoesNotExist:
            logger.error(f"{LoggingContext.ACCOUNTS} Customer Account with ID {account_id} not found")
            return False
        except UserProfile.DoesNotExist:
            logger.error(f"{LoggingContext.ACCOUNTS} UserProfile with ID {user_profile_id} not found")
            return False

    @staticmethod
    @transaction.atomic
    def remove_user_profile_from_account(account_id, user_profile_id):
        try:
            account = UserAccount.objects.get(pk=account_id)
            profile = UserProfile.objects.get(pk=user_profile_id)

            # Check if profile is associated with account
            if profile not in account.user_profiles.all():
                logger.warning(
                    f"{LoggingContext.ACCOUNTS} Profile {user_profile_id} "
                    f"is not associated with customer account {account_id}"
                )
                return False

            # Handle director reassignment if needed
            director_changed = False
            if account.director == profile:
                # For individual accounts, can't remove the director without replacement
                if account.account_type == "individual":
                    raise InvalidUserAccountOperationException("Cannot remove the director from an individual account")

                # For joint accounts, find another profile to be director
                account.director = None
                account.save(update_fields=["director"])
                director_changed = True

            # Remove the profile from the account
            account.user_profiles.remove(profile)

            # If director was changed and there's only one profile left, make it the director
            if director_changed and account.user_profiles.count() == 1:
                account.director = account.user_profiles.first()
                account.save(update_fields=["director"])

            return True
        except UserAccount.DoesNotExist:
            logger.error(f"{LoggingContext.ACCOUNTS} Customer Account with ID {account_id} not found")
            return False
        except UserProfile.DoesNotExist:
            logger.error(f"{LoggingContext.ACCOUNTS} UserProfile with ID {user_profile_id} not found")
            return False
