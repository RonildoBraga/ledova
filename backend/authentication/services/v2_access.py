import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from django.utils import timezone

from authentication.models import AuthSession
from authentication.security import AccessTokenConfiguration, verify_access_token

_SOURCE_ERROR = "Invalid v2 access source."
_SESSION_ERROR = "Invalid v2 access session."


class V2AccessSource(str, Enum):
    BROWSER_COOKIE = "browser_cookie"
    NATIVE_BEARER = "native_bearer"


@dataclass(frozen=True, repr=False)
class V2AccessContext:
    session_id: uuid.UUID
    source: V2AccessSource
    access_expires_at: datetime

    def __repr__(self):
        return "V2AccessContext(session_id=<redacted>, source=<redacted>, access_expires_at=<redacted>)"


class V2AccessSessionError(ValueError):
    pass


def bind_v2_access(
    raw_token,
    *,
    source,
    configuration: AccessTokenConfiguration,
    clock=timezone.now,
):
    if not isinstance(source, V2AccessSource):
        raise TypeError(_SOURCE_ERROR)

    at = clock()
    claims = verify_access_token(
        raw_token,
        configuration=configuration,
        clock=lambda: at,
    )
    client_type = {
        V2AccessSource.BROWSER_COOKIE: AuthSession.ClientType.BROWSER,
        V2AccessSource.NATIVE_BEARER: AuthSession.ClientType.NATIVE,
    }[source]
    session = (
        AuthSession.objects.select_related("user")
        .filter(
            uuid=claims.session_id,
            user_id=claims.user_id,
            client_type=client_type,
            status=AuthSession.Status.ACTIVE,
            absolute_expires_at__gt=at,
            user__is_active=True,
            user__is_email_verified=True,
        )
        .first()
    )
    if session is None or claims.expires_at > session.absolute_expires_at:
        raise V2AccessSessionError(_SESSION_ERROR)

    return session.user, V2AccessContext(
        session_id=session.uuid,
        source=source,
        access_expires_at=claims.expires_at,
    )
