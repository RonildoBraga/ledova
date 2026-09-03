from rest_framework.throttling import SimpleRateThrottle

from authentication.email import EmailError, normalize_email


class EmailRateThrottle(SimpleRateThrottle):
    """Per-address limit for the sign-in, sign-up, verification and resend actions, so one account
    cannot be sprayed or its code guessed from many IPs. Keyed on the body email, or the caller's own
    address for the authenticated resend. The cache is per process (LocMemCache), which is enough
    for the testnet deployment."""

    scope = "auth_email"

    def get_cache_key(self, request, view):
        email = request.data.get("email") if isinstance(request.data, dict) else None
        if not email and request.user.is_authenticated:
            email = request.user.email
        if not isinstance(email, str):
            return None
        try:
            email = normalize_email(email)
        except EmailError:
            email = email.strip().lower()[:254]
        return self.cache_format % {"scope": self.scope, "ident": email}
