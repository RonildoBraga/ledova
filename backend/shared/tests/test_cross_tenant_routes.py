from collections import namedtuple
from datetime import timedelta
from unittest.mock import patch

from django.db import transaction
from django.utils import timezone
from rest_framework.test import APITestCase

from companies.models import (
    LISTING_REQUIRED_DOCUMENTS,
    Company,
    CompanyDocument,
    CompanyStatus,
)
from feature_flags.models import FeatureFlag
from offerings.models import Offering, OfferingStatus, Subscription
from operators.models import Operator
from shared.tests.tenants import (
    make_eligible,
    make_tenant,
    open_to_investors,
    phantom_context,
    route_context,
    snapshot,
)
from tokens.models import ShareIssuanceRequest, ShareToken, ShareTokenStatus, SwapOrder

SIGNATURE = "0x" + "ab" * 65
RECIPIENT = "0x" + "9" * 40
NEW_WALLET_ADDRESS = "0x" + "e" * 40
ALLOWANCE = {
    "token": "0x" + "7" * 40,
    "token_symbol": "TUSD",
    "required_amount": 1500,
    "current_allowance": 0,
    "has_sufficient_allowance": False,
}


def _activate_company(tenant):
    Company.objects.filter(pk=tenant.company.pk).update(status=CompanyStatus.ACTIVE)


def _request_company_info(tenant):
    Company.objects.filter(pk=tenant.company.pk).update(status=CompanyStatus.INFO_REQUIRED)


def _upload_listing_documents(tenant):
    for document_type in LISTING_REQUIRED_DOCUMENTS:
        CompanyDocument.objects.create(
            company=tenant.company,
            document_type=document_type,
            name=document_type.label,
            external_url=f"https://docs.example.test/{tenant.label}/{document_type}",
            file_size=1,
            mime_type="application/pdf",
        )


def _clear_subscriptions(tenant):
    Subscription.objects.filter(user_account=tenant.account).delete()


def _open_the_offering_to_the_actor(tenant):
    make_eligible(tenant)
    Offering.objects.filter(pk=tenant.offering.pk).update(
        status=OfferingStatus.APPROVED, opens_at=timezone.now() - timedelta(days=1)
    )


def _pause_token(tenant):
    ShareToken.objects.filter(pk=tenant.deployed_token.pk).update(status=ShareTokenStatus.PAUSED)


def _create_issuance_request(token, recipient, amount, user, reason="", issuance_type="additional"):
    return ShareIssuanceRequest.objects.create(
        token=token,
        recipient_address=recipient,
        amount=amount,
        reason=reason,
        issuance_type=issuance_type,
        submitted_by=user,
    )


Route = namedtuple("Route", "method path payload foreign prepare", defaults=(None, 404, None))

OFFERING = {
    "exemption": "s708_11_professional",
    "pricePerShare": "2.50",
    "minimumShares": 10,
    "targetShares": 50,
    "capShares": 100,
    "opensAt": "2027-01-01T00:00:00Z",
    "closesAt": "2027-02-01T00:00:00Z",
    "summary": "New tranche",
    "useOfProceeds": "Working capital",
}
SUBSCRIPTION = {
    "userAccount": "{account}",
    "wallet": "{wallet}",
    "quantity": 10,
}
CAPITAL_INCREASE = {
    "additionalShares": 100,
    "newAuthorizedTotal": 1100,
    "purpose": "Growth",
    "boardResolutionReference": "BOARD-NEW",
}
ROUTES = (
    Route("get", "/api/user-profiles/{profile}/"),
    Route("put", "/api/user-profiles/{profile}/", {"fullName": "Renamed", "citizenshipCountry": "{country}"}),
    Route("patch", "/api/user-profiles/{profile}/", {"fullName": "Renamed"}),
    Route("get", "/api/financial-profiles/{financial_profile}/"),
    Route("put", "/api/financial-profiles/{financial_profile}/", {"occupation": "Changed"}),
    Route("patch", "/api/financial-profiles/{financial_profile}/", {"occupation": "Changed"}),
    Route("get", "/api/user-accounts/{account}/"),
    Route("put", "/api/user-accounts/{account}/", {"role": "both"}),
    Route("patch", "/api/user-accounts/{account}/", {"role": "both"}),
    Route("get", "/api/user-preferences/{preferences}/"),
    Route("put", "/api/user-preferences/{preferences}/", {"theme": "light"}),
    Route("patch", "/api/user-preferences/{preferences}/", {"theme": "light"}),
    Route("delete", "/api/user-preferences/{preferences}/"),
    Route("get", "/api/favourite-assets/{favourite}/"),
    Route("delete", "/api/favourite-assets/{favourite}/"),
    Route("get", "/api/device-tokens/{device_token}/"),
    Route("post", "/api/device-tokens/unregister/", {"pushToken": "{push_token}"}),
    Route("get", "/api/notifications/{notification}/"),
    Route("patch", "/api/notifications/{notification}/", {"isRead": True}),
    Route("get", "/api/notification-preferences/{notification_preferences}/"),
    Route("get", "/api/investor-classifications/{investor_classification}/"),
    Route("get", "/api/investor-classifications/{investor_classification}/evidence/"),
    Route("delete", "/api/investor-classifications/{investor_classification}/"),
    Route("patch", "/api/notification-preferences/{notification_preferences}/", {"marketing": True}),
    Route("get", "/api/wallets/{wallet}/"),
    Route(
        "put",
        "/api/wallets/{wallet}/",
        {"userAccount": "{own_account}", "address": "{wallet_address}", "chain": "base"},
    ),
    Route("patch", "/api/wallets/{wallet}/", {"name": "Renamed"}),
    Route("delete", "/api/wallets/{spare_wallet}/"),
    Route("post", "/api/wallets/{wallet}/request-verification/", {}),
    Route("post", "/api/wallets/{wallet}/verify-signature/", {"signature": "0x01"}),
    Route("post", "/api/wallets/{wallet}/sync/", {}),
    Route("get", "/api/wallets/{wallet}/holdings/"),
    Route("post", "/api/wallets/{wallet}/prepare-transfer/", {"toAddress": "0x" + "c" * 40, "amountEth": "0.1"}),
    Route("post", "/api/wallets/{wallet}/broadcast-transfer/", {"signedTransaction": "{signed_transfer}"}),
    Route(
        "post",
        "/api/wallets/",
        {
            "userAccount": "{account}",
            "address": NEW_WALLET_ADDRESS,
            "chain": "ethereum",
            "walletType": "software",
        },
        foreign=400,
    ),
    Route("get", "/api/transactions/{transaction}/"),
    Route("post", "/api/fiat-purchases/transak-widget-url/", {"walletUuid": "{wallet}"}),
    Route("get", "/api/portfolios/{portfolio}/"),
    Route("put", "/api/portfolios/{portfolio}/", {"name": "Renamed"}),
    Route("patch", "/api/portfolios/{portfolio}/", {"name": "Renamed"}),
    Route("delete", "/api/portfolios/{portfolio}/"),
    Route("get", "/api/portfolios/{portfolio}/snapshots/"),
    Route("post", "/api/portfolios/{portfolio}/add-wallet/", {"walletUuid": "{own_spare_wallet}"}),
    Route("post", "/api/portfolios/{own_portfolio}/add-wallet/", {"walletUuid": "{spare_wallet}"}),
    Route("post", "/api/portfolios/{portfolio}/remove-wallet/", {"walletUuid": "{own_wallet}"}),
    Route("post", "/api/portfolios/{own_portfolio}/remove-wallet/", {"walletUuid": "{wallet}"}),
    Route("get", "/api/v1/companies/{company}/"),
    Route("put", "/api/v1/companies/{company}/", {"name": "Renamed", "acn": "{acn}"}),
    Route("patch", "/api/v1/companies/{company}/", {"name": "Renamed"}),
    Route("delete", "/api/v1/companies/{company}/", prepare=_clear_subscriptions),
    Route("post", "/api/v1/companies/{company}/submit/", {"confirm": True}, prepare=_upload_listing_documents),
    Route("post", "/api/v1/companies/{company}/resubmit/", {"response": "Done"}, prepare=_request_company_info),
    Route("post", "/api/v1/companies/{company}/withdraw/", {}),
    Route("get", "/api/v1/companies/{company}/stats/"),
    Route("get", "/api/v1/companies/{company}/application-status/"),
    Route("get", "/api/v1/companies/{company}/documents/"),
    Route(
        "post",
        "/api/v1/companies/{company}/documents/",
        {
            "document_type": "bank_statement",
            "name": "Statement",
            "external_url": "https://docs.example.test/statement",
            "file_size": 1,
            "mime_type": "application/pdf",
        },
    ),
    Route("get", "/api/v1/companies/{company}/documents/{company_document}/"),
    Route("get", "/api/v1/companies/{own_company}/documents/{company_document}/"),
    Route("get", "/api/v1/companies/{company}/documents/{company_document}/file/"),
    Route("get", "/api/v1/companies/{own_company}/documents/{company_document}/file/"),
    Route("delete", "/api/v1/companies/{company}/documents/{company_document}/"),
    Route("get", "/api/v1/tokens/{token}/"),
    Route("put", "/api/v1/tokens/{token}/", {"name": "Renamed"}),
    Route("patch", "/api/v1/tokens/{token}/", {"name": "Renamed"}),
    Route("delete", "/api/v1/tokens/{token}/"),
    Route("post", "/api/v1/tokens/{token}/deploy/", {}, prepare=_activate_company),
    Route("post", "/api/v1/tokens/{deployed_token}/pause/", {}),
    Route("post", "/api/v1/tokens/{deployed_token}/unpause/", {}, prepare=_pause_token),
    Route(
        "post",
        "/api/v1/tokens/{deployed_token}/issue/",
        {"recipient": RECIPIENT, "amount": 7, "reason": "Owner", "issuanceType": "additional"},
    ),
    Route("get", "/api/v1/tokens/{deployed_token}/issuances/"),
    Route("get", "/api/v1/tokens/{deployed_token}/holders/"),
    Route("get", "/api/v1/tokens/{deployed_token}/register/export/"),
    Route(
        "post",
        "/api/v1/tokens/",
        {"company": "{company}", "name": "New shares", "symbol": "NEW", "totalSupply": "1000"},
        foreign=400,
    ),
    Route("get", "/api/v1/tokens/capital-increases/{capital_increase}/"),
    Route("put", "/api/v1/tokens/capital-increases/{capital_increase}/", CAPITAL_INCREASE),
    Route("patch", "/api/v1/tokens/capital-increases/{capital_increase}/", {"purpose": "Changed"}),
    Route("delete", "/api/v1/tokens/capital-increases/{capital_increase}/"),
    Route("post", "/api/v1/tokens/capital-increases/{capital_increase}/submit/", {}),
    Route("post", "/api/v1/tokens/capital-increases/", {"token": "{deployed_token}", **CAPITAL_INCREASE}),
    Route("get", "/api/v1/offerings/{offering}/"),
    Route("put", "/api/v1/offerings/{offering}/", {"token": "{deployed_token}", **OFFERING}),
    Route("patch", "/api/v1/offerings/{offering}/", {"summary": "Changed"}),
    Route("delete", "/api/v1/offerings/{offering}/", prepare=_clear_subscriptions),
    Route("post", "/api/v1/offerings/{offering}/submit/", {}, prepare=_activate_company),
    Route("post", "/api/v1/offerings/{offering}/withdraw/", {}),
    Route("get", "/api/v1/offerings/{offering}/subscriptions/"),
    Route("post", "/api/v1/offerings/", {"token": "{deployed_token}", **OFFERING}, foreign=400),
    Route("get", "/api/v1/subscriptions/{subscription}/"),
    Route("post", "/api/v1/subscriptions/{subscription}/submit/", {}, prepare=_open_the_offering_to_the_actor),
    Route("post", "/api/v1/subscriptions/{subscription}/withdraw/", {"reason": "Changed my mind"}),
    Route(
        "post",
        "/api/v1/subscriptions/",
        {"offering": "{offering}", **SUBSCRIPTION},
        foreign=400,
        prepare=_open_the_offering_to_the_actor,
    ),
    Route("get", "/api/v1/trading/orders/{order}/"),
    Route("post", "/api/v1/trading/orders/{order}/cancel/", {"message": "cancel", "signature": SIGNATURE}),
    Route("get", "/api/v1/trading/orders/{order}/cancel/message/"),
    Route("post", "/api/v1/trading/orders/{order}/modify/", {"message": "modify", "signature": SIGNATURE}),
    Route("post", "/api/v1/trading/orders/{order}/modify/message/", {"newQuantity": 5}),
    Route("get", "/api/v1/trading/orders/{order}/modifications/"),
    Route("get", "/api/v1/trading/orders/{order}/swap/?wallet_address={own_wallet_address}"),
    Route(
        "post",
        "/api/v1/trading/orders/{order}/swap/sign/",
        {"signature": SIGNATURE, "signerAddress": "{own_wallet_address}"},
    ),
    Route("get", "/api/v1/trading/orders/{order}/swap/approval-status/?wallet_address={own_wallet_address}"),
    Route("get", "/api/v1/trading/orders/{order}/swap/approval-data/?wallet_address={own_wallet_address}"),
    Route("get", "/api/v1/documents/{document}/"),
    Route("get", "/api/v1/documents/{document}/file/"),
    Route("delete", "/api/v1/documents/{document}/"),
)


OPERATOR_ROUTES = (
    Route("get", "/api/v1/companies/{company}/api-key/"),
    Route("post", "/api/v1/companies/{company}/api-key/", {}),
    Route(
        "post",
        "/api/v1/companies/{company}/status/",
        {"status": "warning", "reason": "Review"},
        prepare=_activate_company,
    ),
)


LIST_ROUTES = (
    ("/api/user-profiles/", ("profile",)),
    ("/api/financial-profiles/", ("financial_profile",)),
    ("/api/user-accounts/", ("account",)),
    ("/api/favourite-assets/", ("favourite",)),
    ("/api/device-tokens/", ("device_token",)),
    ("/api/notifications/", ("notification",)),
    ("/api/investor-classifications/", ("investor_classification",)),
    ("/api/wallets/", ("wallet", "spare_wallet")),
    ("/api/wallets/{wallet}/holdings/", ("holding",)),
    ("/api/transactions/", ("transaction",)),
    ("/api/portfolios/", ("portfolio",)),
    ("/api/portfolios/{portfolio}/snapshots/?start_date=2026-09-01&end_date=2026-09-01", ("series_point",)),
    ("/api/v1/companies/", ("company",)),
    ("/api/v1/companies/{company}/documents/", ("company_document",)),
    ("/api/v1/tokens/", ("token", "deployed_token")),
    ("/api/v1/tokens/capital-increases/", ("capital_increase",)),
    ("/api/v1/offerings/", ("offering",)),
    ("/api/v1/subscriptions/", ("subscription",)),
    ("/api/v1/trading/orders/", ("order", "counter_order")),
    ("/api/v1/documents/", ("document",)),
)
SINGLETON_ROUTES = (
    ("/api/user-preferences/", "preferences"),
    ("/api/notification-preferences/", "notification_preferences"),
)

DIRECTORY_ROUTES = (Route("get", "/api/v1/directory/tokens/{deployed_token}/"),)

MARKET_ROUTES = (
    Route("get", "/api/v1/trading/tokens/{deployed_token}/"),
    Route("get", "/api/v1/trading/tokens/{deployed_token}/market-data/"),
    Route("get", "/api/v1/trading/tokens/{deployed_token}/order-book/"),
)

GLOBAL_ROUTES = ("/api/operator/",)
RAILS = {"bankBsb": "062000"}


def _body(response):
    return b"<streamed file>" if response.streaming else response.content


def _fill(value, context):
    if isinstance(value, str):
        return value.format_map(context)
    if isinstance(value, dict):
        return {key: _fill(item, context) for key, item in value.items()}
    return value


class CrossTenantRouteMatrixTest(APITestCase):
    def setUp(self):
        FeatureFlag.objects.update_or_create(name="trading_enabled", defaults={"enabled": True})
        self._patch("rest_framework.throttling.SimpleRateThrottle.allow_request", return_value=True)
        self.services = []
        wallet_sync = self._service("wallets.views.wallet.WalletSyncService")
        wallet_sync.sync_wallet.return_value = {"status": "success"}
        wallet_transfer = self._service("wallets.views.wallet.TransferService")
        wallet_transfer.prepare_transfer.return_value = {"transaction": {}}
        wallet_transfer.broadcast_transfer.return_value = {"success": True}
        self._service("wallets.services.verification.verify_wallet_signature", return_value=True)
        self._service("wallets.tasks.sync_wallet").defer.return_value = "job"
        self._service("wallets.views.fiat_purchase.generate_transak_widget_url", return_value="https://widget.test")
        self._service("companies.services.company.send_push_notification")
        self._service("offerings.services.offering.send_push_notification")
        self._service("tokens.tasks.deploy_share_token_task")
        share_tokens = self._service("tokens.views.share_token.ShareTokenService").return_value
        share_tokens.create_issuance_request.side_effect = _create_issuance_request
        trading_orders = self._service("tokens.views.trading_order.TradingOrderService")
        trading_orders.cancel_order.side_effect = lambda order: order
        trading_orders.get_order_cancel_message.return_value = {}
        modifications = self._service("tokens.views.trading_order.OrderModificationService").return_value
        modifications.generate_modification_message.return_value = {}
        modifications.apply_modification.side_effect = lambda order, **kwargs: (order, {})
        modifications.get_modification_history.return_value = {}
        swaps = self._service("tokens.views.trading_order.AtomicSwapService").return_value
        swaps.contract_address = "0x" + "8" * 40
        swaps.find_swap_order_by_transfer_order.side_effect = SwapOrder.objects.for_transfer_order
        swaps.submit_signature.side_effect = lambda swap_order, **kwargs: swap_order
        swaps.get_typed_data.return_value = {}
        swaps.check_swap_allowances.return_value = {"seller": ALLOWANCE, "buyer": ALLOWANCE}
        swaps.get_approval_transaction_data.return_value = {}

        self.actors = (make_tenant("alice"), make_tenant("staff", staff=True), make_tenant("root", superuser=True))
        self.other = make_tenant("bob")

    def _patch(self, target, **kwargs):
        patcher = patch(target, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def _service(self, target, **kwargs):
        mock = self._patch(target, **kwargs)
        self.services.append(mock)
        return mock

    def send(self, route, actor, context):
        context = {**context, **{f"own_{key}": value for key, value in route_context(actor).items()}}
        request = getattr(self.client, route.method)
        return request(route.path.format_map(context), _fill(route.payload, context), format="json")

    @staticmethod
    def rows(response):
        body = response.json()
        return body.get("results", body) if isinstance(body, dict) else body

    @staticmethod
    def masked(response, context):
        text = _body(response).decode()
        for value in context.values():
            text = text.replace(value, "<target>")
        return text

    def test_foreign_rows_are_not_found_and_left_untouched(self):
        before = snapshot(self.other)
        foreign = route_context(self.other)
        phantom = phantom_context(self.other)

        for actor in self.actors:
            self.client.force_authenticate(actor.user)
            for route in ROUTES:
                foreign_response = self.send(route, actor, foreign)
                phantom_response = self.send(route, actor, phantom)
                with self.subTest(actor=actor.label, route=f"{route.method} {route.path}"):
                    self.assertEqual(foreign_response.status_code, route.foreign, foreign_response.content)
                    self.assertEqual(phantom_response.status_code, route.foreign, phantom_response.content)
                    self.assertEqual(self.masked(foreign_response, foreign), self.masked(phantom_response, phantom))

        self.assertEqual(snapshot(self.other), before)
        for service in self.services:
            self.assertEqual(service.mock_calls, [])

    def test_own_rows_resolve_for_every_actor(self):
        for actor in self.actors:
            self.client.force_authenticate(actor.user)
            own = route_context(actor)
            for route in ROUTES:
                with self.subTest(actor=actor.label, route=f"{route.method} {route.path}"):

                    with transaction.atomic():
                        if route.prepare:
                            route.prepare(actor)
                        response = self.send(route, actor, own)
                        transaction.set_rollback(True)
                    self.assertIn(response.status_code, (200, 201, 202, 204), _body(response))

    def test_operator_routes_are_staff_only_and_reach_every_tenant(self):
        foreign = route_context(self.other)
        phantom = phantom_context(self.other)
        for actor in self.actors:
            self.client.force_authenticate(actor.user)
            for route in OPERATOR_ROUTES:
                with self.subTest(actor=actor.label, route=f"{route.method} {route.path}"):
                    with transaction.atomic():
                        if route.prepare:
                            route.prepare(self.other)
                        foreign_response = self.send(route, actor, foreign)
                        phantom_response = self.send(route, actor, phantom)
                        transaction.set_rollback(True)
                    if actor.user.is_staff:
                        self.assertEqual(foreign_response.status_code, 200, foreign_response.content)
                        self.assertEqual(phantom_response.status_code, 404, phantom_response.content)
                    else:
                        self.assertEqual(foreign_response.status_code, 403, foreign_response.content)
                        self.assertEqual(phantom_response.status_code, 403, phantom_response.content)
                        self.assertEqual(self.masked(foreign_response, foreign), self.masked(phantom_response, phantom))

    def test_directory_and_market_routes_reach_every_tenant_and_hide_phantom_rows(self):
        foreign = route_context(self.other)
        phantom = phantom_context(self.other)
        for actor in self.actors:
            self.client.force_authenticate(actor.user)
            for route in DIRECTORY_ROUTES + MARKET_ROUTES:
                with self.subTest(actor=actor.label, route=f"{route.method} {route.path}"):
                    with transaction.atomic():
                        make_eligible(actor)
                        open_to_investors(self.other)
                        foreign_response = self.send(route, actor, foreign)
                        phantom_response = self.send(route, actor, phantom)
                        transaction.set_rollback(True)
                    self.assertEqual(foreign_response.status_code, 200, foreign_response.content)
                    self.assertEqual(phantom_response.status_code, 404, phantom_response.content)

    def test_the_market_answers_without_the_issuers_directory_opt_in(self):
        foreign = route_context(self.other)
        for actor in self.actors:
            self.client.force_authenticate(actor.user)
            for route in MARKET_ROUTES + DIRECTORY_ROUTES:
                with self.subTest(actor=actor.label, route=f"{route.method} {route.path}"):
                    with transaction.atomic():
                        make_eligible(actor)
                        foreign_response = self.send(route, actor, foreign)
                        transaction.set_rollback(True)
                    expected = 200 if route in MARKET_ROUTES else 404
                    self.assertEqual(foreign_response.status_code, expected, foreign_response.content)

    def test_directory_and_market_routes_are_empty_and_not_found_without_eligibility(self):
        foreign = route_context(self.other)
        phantom = phantom_context(self.other)
        for actor in self.actors:
            self.client.force_authenticate(actor.user)
            for route in DIRECTORY_ROUTES + MARKET_ROUTES:
                with self.subTest(actor=actor.label, route=f"{route.method} {route.path}"):
                    with transaction.atomic():
                        open_to_investors(self.other)
                        foreign_response = self.send(route, actor, foreign)
                        phantom_response = self.send(route, actor, phantom)
                        transaction.set_rollback(True)
                    self.assertEqual(foreign_response.status_code, 404, foreign_response.content)
                    self.assertEqual(phantom_response.status_code, 404, phantom_response.content)
                    self.assertEqual(self.masked(foreign_response, foreign), self.masked(phantom_response, phantom))

    def test_collection_routes_return_only_the_actors_rows(self):
        for actor in self.actors:
            self.client.force_authenticate(actor.user)
            own = route_context(actor)
            for path, keys in LIST_ROUTES:
                response = self.client.get(path.format_map(own))
                with self.subTest(actor=actor.label, path=path):
                    self.assertEqual(response.status_code, 200, response.content)
                    self.assertEqual({row["uuid"] for row in self.rows(response)}, {own[key] for key in keys})
            for path, key in SINGLETON_ROUTES:
                response = self.client.get(path)
                with self.subTest(actor=actor.label, path=path):
                    self.assertEqual(response.status_code, 200, response.content)
                    self.assertEqual(response.json()["uuid"], own[key])

    def test_global_singleton_routes_answer_every_actor_and_refuse_anonymous(self):
        operator = Operator.get()
        operator.bank_bsb = "062000"
        operator.save(update_fields=["bank_bsb"])
        for path in GLOBAL_ROUTES:
            bodies = {}
            for actor in self.actors:
                self.client.force_authenticate(actor.user)
                response = self.client.get(path)
                with self.subTest(actor=actor.label, path=path):
                    self.assertEqual(response.status_code, 200, response.content)
                bodies[actor.label] = response.json()
            rails = {label: body.pop("paymentInstructions") for label, body in bodies.items()}
            self.assertEqual(rails, {"alice": None, "staff": RAILS, "root": RAILS})
            self.assertEqual(len({str(body) for body in bodies.values()}), 1)
            self.client.force_authenticate(None)
            self.assertEqual(self.client.get(path).status_code, 401)

    def test_the_operator_rails_follow_the_eligibility_predicate_not_the_session(self):
        operator = Operator.get()
        operator.bank_bsb = "062000"
        operator.save(update_fields=["bank_bsb"])
        alice = self.actors[0]
        self.client.force_authenticate(alice.user)

        self.assertIsNone(self.client.get(GLOBAL_ROUTES[0]).json()["paymentInstructions"])

        with transaction.atomic():
            make_eligible(alice)
            self.assertEqual(self.client.get(GLOBAL_ROUTES[0]).json()["paymentInstructions"], RAILS)
            transaction.set_rollback(True)
