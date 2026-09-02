from dataclasses import dataclass
from enum import Enum

from django.contrib.auth.models import BaseUserManager

from authentication.security.v2_email import (
    V2_EMAIL_ERROR,
    V2EmailError,
    normalize_v2_email,
    v2_email_destination_expression,
)


class V2EmailLookupState(Enum):
    ABSENT = "absent"
    UNIQUE = "unique"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, repr=False)
class V2EmailLookupResult:
    state: V2EmailLookupState
    user: object | None = None

    def __post_init__(self):
        has_user = self.user is not None
        if has_user != (self.state is V2EmailLookupState.UNIQUE):
            raise ValueError("Invalid v2 email lookup result.")

    def __repr__(self):
        return "V2EmailLookupResult(<redacted>)"


class CustomUserManager(BaseUserManager):

    @classmethod
    def normalize_email(cls, email):
        return normalize_v2_email(email)

    def _v2_email_candidates(self, destination_key):
        normalized = normalize_v2_email(destination_key)
        if normalized != destination_key:
            raise V2EmailError(V2_EMAIL_ERROR)

        return (
            self.get_queryset()
            .alias(v2_email_destination_key=v2_email_destination_expression())
            .filter(v2_email_destination_key=destination_key)
            .order_by("pk")[:2]
        )

    @staticmethod
    def _v2_email_result(rows):
        if not rows:
            return V2EmailLookupResult(V2EmailLookupState.ABSENT)
        if len(rows) == 1:
            return V2EmailLookupResult(V2EmailLookupState.UNIQUE, rows[0])
        return V2EmailLookupResult(V2EmailLookupState.AMBIGUOUS)

    def resolve_v2_email(self, destination_key):
        return self._v2_email_result(list(self._v2_email_candidates(destination_key)))

    async def aresolve_v2_email(self, destination_key):
        rows = [row async for row in self._v2_email_candidates(destination_key)]
        return self._v2_email_result(rows)

    def get_by_natural_key(self, username):
        try:
            destination_key = normalize_v2_email(username)
            result = self.resolve_v2_email(destination_key)
        except V2EmailError:
            raise self.model.DoesNotExist from None
        if result.state is V2EmailLookupState.UNIQUE:
            return result.user
        raise self.model.DoesNotExist

    async def aget_by_natural_key(self, username):
        try:
            destination_key = normalize_v2_email(username)
            result = await self.aresolve_v2_email(destination_key)
        except V2EmailError:
            raise self.model.DoesNotExist from None
        if result.state is V2EmailLookupState.UNIQUE:
            return result.user
        raise self.model.DoesNotExist

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("The Email field must be set")
        destination_key = self.normalize_email(email)
        if self.resolve_v2_email(destination_key).state is not V2EmailLookupState.ABSENT:
            raise ValueError("V2 email is unavailable.")
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
