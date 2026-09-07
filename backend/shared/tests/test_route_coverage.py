import re

from django.test import SimpleTestCase
from django.urls import get_resolver
from django.urls.resolvers import URLPattern, URLResolver

from shared.tests import test_cross_tenant_routes as matrix

PARAMETER = re.compile(r"\(\?P<[^>]+>[^)]*\)")
TEMPLATE = re.compile(r"\{[a-z_]+\}")
IGNORED_PREFIXES = ("/admin", "/static", "/media", "/api-auth", "/health")
BODYLESS = {"head", "options", "trace"}

UNAUTHENTICATED_AUTH = "Unauthenticated auth surface: there is no session yet, so there is no tenant to cross."
PROVIDER_WEBHOOK = "Provider webhook: no session, authenticated by signature, and it names its own subject."
GLOBAL_CATALOGUE = "Global catalogue shared by every tenant and deliberately not owner-scoped."
CREATES_OWN_ROW = "Creation route: writes a row owned by the caller and accepts no writable relation."
CREATES_OWN_ROW_SCOPED_FK = (
    "Creation route owned by the caller. Every writable relation it accepts is scoped before the body "
    "can reach it: either declared against an already-filtered catalogue queryset, or declared as "
    "objects.none() and re-scoped in the serializer's get_fields(). Either way a foreign identifier in "
    "the body cannot name a row the caller cannot already see."
)
SELF_SCOPED = "Acts only on the caller's own rows and takes no identifier."
ELIGIBILITY_SCOPED = (
    "Cross-tenant listing scoped by users.services.eligibility rather than by owner, "
    "and the documented exception in ARCHITECTURE.md. Pinned by MARKET_ROUTES and DIRECTORY_ROUTES."
)
SIGNED_RELAY = (
    "Relays an already-signed transaction and takes no tenant identifier at all, so the signature is the only "
    "thing that can carry tenancy. TradingTransferViewSet.broadcast recovers the sender with "
    "decode_signed_transaction and hands it to tokens.trading_wallet_access.resolve_verified_evm_wallets, "
    "which answers 404 unless the caller holds a verified wallet at that address - the same call the prepare "
    "route beside it makes. BroadcastTransferSerializer (tokens/serializers/transfer_order.py) refuses a "
    "foreign chain id, a contract creation and any target outside known_contract_addresses() before that. "
    "Note what this reason may not say: that a caller cannot produce a signature it does not hold. A signed "
    "transaction is public from the moment it is broadcast, so anyone can replay one - see issue #190. "
    "Pinned by tokens/tests/test_trading_transfer_broadcast.py."
)
NOT_MATRIX_AUTHENTICABLE = (
    "It cannot become a ROUTES row however well it reads as one: the cross-tenant matrix authenticates "
    "through DRF, and a plain Django view never sees force_authenticate, so every case there answers 401 "
    "and no assertion about tenancy is reachable. A route in this position stays exempt with a reason "
    "naming its scoping call and the test file that pins it instead."
)
ELIGIBILITY_SCOPED_ASYNC = (
    "Scoped by users.services.eligibility exactly as the market listing beside it is: "
    "tokens.services.trading_events.resolve_streamable_token_uuid returns None unless "
    "investor_eligibility(user).is_eligible, and only then asks whether the token is deployed with a "
    "contract address - the same queryset the market listing serves. An ineligible caller therefore gets "
    "the same 404 as a phantom uuid, without a token lookup, so the two are indistinguishable by timing "
    "as well as by body. Pinned by tokens/tests/test_trading_events_authorization.py. "
) + NOT_MATRIX_AUTHENTICABLE
STAFF_UNSCOPED = (
    "Staff-only and deliberately unscoped: CompanyViewSet.get_queryset returns Company.objects.all() "
    "for its administrative actions, so an operator reaches every company by design."
)
STAFF_WHITELIST = "Staff-only whitelist administration: the operator acts across every tenant by design."
BODY_IDENTIFIED = "Identifies its subject in the request body rather than the path, so the matrix cannot template it."
CHAIN_ADDRESS_READ = "Reads the chain for a bare address, which belongs to no tenant row."

EXEMPT = {
    ("post", "/api/signin/"): UNAUTHENTICATED_AUTH,
    ("post", "/api/signup/"): UNAUTHENTICATED_AUTH,
    ("post", "/api/signout/"): UNAUTHENTICATED_AUTH,
    ("post", "/api/signout-all/"): UNAUTHENTICATED_AUTH,
    ("post", "/api/token/refresh/"): UNAUTHENTICATED_AUTH,
    ("post", "/api/change-password/"): UNAUTHENTICATED_AUTH,
    ("post", "/api/email-verification/"): UNAUTHENTICATED_AUTH,
    ("post", "/api/resend-verification/"): UNAUTHENTICATED_AUTH,
    ("get", "/api/auth/verify/"): UNAUTHENTICATED_AUTH,
    ("post", "/webhooks/alchemy/"): PROVIDER_WEBHOOK,
    ("post", "/webhooks/kycaid/"): PROVIDER_WEBHOOK,
    ("post", "/webhooks/kycaid/crypto/"): PROVIDER_WEBHOOK,
    ("post", "/webhooks/sumsub/"): PROVIDER_WEBHOOK,
    ("get", "/api/assets/"): GLOBAL_CATALOGUE,
    ("get", "/api/assets/{}/"): GLOBAL_CATALOGUE,
    ("get", "/api/assets/{}/snapshots/"): GLOBAL_CATALOGUE,
    ("get", "/api/assets/exchange-rates/"): GLOBAL_CATALOGUE,
    ("get", "/api/feature-flags/"): GLOBAL_CATALOGUE,
    ("get", "/api/feature-flags/{}/"): GLOBAL_CATALOGUE,
    ("post", "/api/device-tokens/"): CREATES_OWN_ROW,
    ("post", "/api/device-tokens/register/"): CREATES_OWN_ROW,
    ("post", "/api/financial-profiles/"): CREATES_OWN_ROW,
    ("post", "/api/notification-preferences/"): CREATES_OWN_ROW,
    ("post", "/api/user-accounts/"): CREATES_OWN_ROW,
    ("post", "/api/user-profiles/"): CREATES_OWN_ROW_SCOPED_FK,
    ("post", "/api/v1/companies/"): CREATES_OWN_ROW_SCOPED_FK,
    ("post", "/api/v1/documents/"): CREATES_OWN_ROW,
    ("get", "/api/notifications/unread-count/"): SELF_SCOPED,
    ("post", "/api/notifications/mark-all-read/"): SELF_SCOPED,
    ("get", "/api/user-profiles/export-data/"): SELF_SCOPED,
    ("post", "/api/user-profiles/delete-account/"): SELF_SCOPED,
    ("get", "/api/investor-classifications/eligibility/"): SELF_SCOPED,
    ("get", "/api/users/identity-verification/status/"): SELF_SCOPED,
    ("post", "/api/users/identity-verification/token/"): SELF_SCOPED,
    ("get", "/api/v1/directory/tokens/"): ELIGIBILITY_SCOPED,
    ("get", "/api/v1/trading/tokens/"): ELIGIBILITY_SCOPED,
    ("get", "/api/v1/trading/events/stream/"): ELIGIBILITY_SCOPED_ASYNC,
    ("post", "/api/v1/trading/transfers/broadcast/"): SIGNED_RELAY,
    ("get", "/api/v1/companies/{}/api-key/"): STAFF_UNSCOPED,
    ("post", "/api/v1/companies/{}/api-key/"): STAFF_UNSCOPED,
    ("post", "/api/v1/companies/{}/status/"): STAFF_UNSCOPED,
    ("get", "/api/v1/whitelist/"): STAFF_WHITELIST,
    ("get", "/api/v1/whitelist/{}/"): STAFF_WHITELIST,
    ("get", "/api/v1/whitelist/entry/{}/"): STAFF_WHITELIST,
    ("get", "/api/v1/whitelist/export/"): STAFF_WHITELIST,
    ("post", "/api/v1/whitelist/add/"): STAFF_WHITELIST,
    ("post", "/api/v1/whitelist/batch-add/"): STAFF_WHITELIST,
    ("post", "/api/v1/whitelist/remove/"): STAFF_WHITELIST,
    ("post", "/api/v1/whitelist/sync/{}/"): STAFF_WHITELIST,
    ("post", "/api/wallets/batch-check-balances/"): BODY_IDENTIFIED,
    ("get", "/api/v1/trading/whitelist/{}/status/"): CHAIN_ADDRESS_READ,
}


def _walk(patterns, prefix=""):
    for entry in patterns:
        raw = str(entry.pattern)
        if isinstance(entry, URLResolver):
            yield from _walk(entry.url_patterns, prefix + raw)
        elif isinstance(entry, URLPattern):
            yield prefix + raw, entry.callback


def _normalise(path):
    path = PARAMETER.sub("{}", path)
    path = path.replace("^", "").replace("$", "").replace("\\.", ".")
    path = re.sub(r"<[^:>]+:[^>]+>", "{}", path)
    path = re.sub(r"<[^>]+>", "{}", path)
    path = "/" + path.lstrip("/")
    return path if path.endswith("/") else path + "/"


def _methods(callback):
    view = getattr(callback, "cls", None) or getattr(callback, "view_class", None)
    allowed = set(getattr(view, "http_method_names", []) or []) if view else set()
    actions = getattr(callback, "actions", None)
    if actions:
        methods = (set(actions) & allowed) if allowed else set(actions)
    elif view:
        methods = {name for name in allowed if hasattr(view, name)}
    else:
        methods = {"get"}
    return methods - BODYLESS


def registered_routes():
    routes = set()
    for path, callback in _walk(get_resolver().url_patterns):
        normalised = _normalise(path)
        if normalised.startswith(IGNORED_PREFIXES) or ".{}" in normalised:
            continue
        view = getattr(callback, "cls", None)
        if getattr(view, "__name__", "") == "APIRootView":
            continue
        for method in _methods(callback):
            routes.add((method, normalised))
    return routes


def matrix_routes():
    routes = set()

    def add(method, path):
        routes.add((method.lower(), TEMPLATE.sub("{}", path.split("?")[0])))

    for route in matrix.ROUTES + matrix.DIRECTORY_ROUTES + matrix.MARKET_ROUTES:
        add(route.method, route.path)
    for path, _ in matrix.LIST_ROUTES:
        add("get", path)
    for path, _ in matrix.SINGLETON_ROUTES:
        add("get", path)
    for path in matrix.GLOBAL_ROUTES:
        add("get", path)
    return routes


class RouteCoverageTest(SimpleTestCase):

    def test_every_registered_route_is_pinned_by_the_matrix_or_exempt_with_a_reason(self):
        unclassified = sorted(registered_routes() - matrix_routes() - set(EXEMPT))

        self.assertEqual(
            unclassified,
            [],
            "New routes are neither in the cross-tenant matrix nor exempt. Add each to ROUTES/LIST_ROUTES in "
            "test_cross_tenant_routes.py so a foreign uuid is proven to 404, or to EXEMPT here with the reason "
            f"it cannot leak another tenant's row: {unclassified}",
        )

    def test_no_exemption_outlives_the_route_it_excuses(self):
        stale = sorted(set(EXEMPT) - registered_routes())

        self.assertEqual(stale, [], f"These routes no longer exist; delete their exemptions: {stale}")

    def test_no_matrix_entry_points_at_a_route_that_no_longer_exists(self):
        stale = sorted(matrix_routes() - registered_routes())

        self.assertEqual(stale, [], f"The matrix pins routes that are not registered: {stale}")

    def test_every_exemption_states_a_reason(self):
        thin = sorted(route for route, reason in EXEMPT.items() if len(reason) < 40)

        self.assertEqual(thin, [], f"An exemption needs a reason a reviewer can disagree with: {thin}")
