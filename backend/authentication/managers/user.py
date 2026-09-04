from dataclasses import dataclass
from enum import Enum

from django.contrib.auth.models import BaseUserManager

from authentication.email import EMAIL_ERROR, EmailError, email_destination_expression
from authentication.email import normalize_email as normalize_email_address


class EmailLookupState(Enum):
    ABSENT = "absent"
    UNIQUE = "unique"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, repr=False)
class EmailLookupResult:
    state: EmailLookupState
    user: object | None = None

    def __post_init__(self):
        has_user = self.user is not None
        if has_user != (self.state is EmailLookupState.UNIQUE):
            raise ValueError("Invalid email lookup result.")

    def __repr__(self):
        return "EmailLookupResult(<redacted>)"


class CustomUserManager(BaseUserManager):

    @classmethod
    def normalize_email(cls, email):
        return normalize_email_address(email)

    def _email_candidates(self, destination_key):
        normalized = normalize_email_address(destination_key)
        if normalized != destination_key:
            raise EmailError(EMAIL_ERROR)

        return (
            self.get_queryset()
            .alias(email_destination_key=email_destination_expression())
            .filter(email_destination_key=destination_key)
            .order_by("pk")[:2]
        )

    @staticmethod
    def _email_result(rows):
        if not rows:
            return EmailLookupResult(EmailLookupState.ABSENT)
        if len(rows) == 1:
            return EmailLookupResult(EmailLookupState.UNIQUE, rows[0])
        return EmailLookupResult(EmailLookupState.AMBIGUOUS)

    def resolve_email(self, destination_key):
        return self._email_result(list(self._email_candidates(destination_key)))

    async def aresolve_email(self, destination_key):
        rows = [row async for row in self._email_candidates(destination_key)]
        return self._email_result(rows)

    def get_by_natural_key(self, username):
        try:
            destination_key = normalize_email_address(username)
            result = self.resolve_email(destination_key)
        except EmailError:
            raise self.model.DoesNotExist from None
        if result.state is EmailLookupState.UNIQUE:
            return result.user
        raise self.model.DoesNotExist

    async def aget_by_natural_key(self, username):
        try:
            destination_key = normalize_email_address(username)
            result = await self.aresolve_email(destination_key)
        except EmailError:
            raise self.model.DoesNotExist from None
        if result.state is EmailLookupState.UNIQUE:
            return result.user
        raise self.model.DoesNotExist

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("The Email field must be set")
        destination_key = self.normalize_email(email)
        if self.resolve_email(destination_key).state is not EmailLookupState.ABSENT:
            raise ValueError("Email is unavailable.")
        user = self.model(email=destination_key, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("is_email_verified", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        if extra_fields.get("is_active") is not True:
            raise ValueError("Superuser must have is_active=True.")

        return self.create_user(email, password, **extra_fields)
