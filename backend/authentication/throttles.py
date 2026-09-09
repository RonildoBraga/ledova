from rest_framework.throttling import SimpleRateThrottle

from authentication.email import EmailError, normalize_email


class EmailRateThrottle(SimpleRateThrottle):

    scope = "auth_email"

    def allow_request(self, request, view):
        take_slot = getattr(self.cache, "take_rate_slot", None)
        if take_slot is None:
            return super().allow_request(request, view)
        key = self.get_cache_key(request, view)
        if self.rate is None or key is None:
            return True
        allowed, self.shared_wait = take_slot(key, self.num_requests, self.duration)
        return allowed

    def wait(self):
        if hasattr(self, "shared_wait"):
            return self.shared_wait
        return super().wait()

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
