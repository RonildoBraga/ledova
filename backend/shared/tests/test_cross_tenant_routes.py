from collections import namedtuple
from contextlib import contextmanager
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITransactionTestCase

from companies.models import (
    LISTING_REQUIRED_DOCUMENTS,
    Company,
    CompanyDocument,
    CompanyRegistryCheck,
    CompanyStatus,
)
from companies.tests.registry_fixtures import DECLARATION
from feature_flags.models import FeatureFlag
from integrations.abr.client import RegistryObservation
from offerings.models import Offering, OfferingStatus, Subscription
from operators.models import Operator
from shared.db import atomic, current_alias, use_operator
from shared.tests.scoped import RunsOnTheScopedConnection
from shared.tests.settlement import SYNTHETIC_SETTLEMENT_CONTRACT
from shared.tests.tenants import (
    an_acn,
    make_eligible,
    make_tenant,
    open_to_investors,
    phantom_context,
    route_context,
    snapshot,
)
from shared.tests.upload_fixtures import StubUploadDependencies, pdf_bytes
from tokens.models import (
    ShareIssuanceRequest,
    ShareToken,
    ShareTokenStatus,
    SwapOrder,
    TransferOrder,
)
from tokens.tests.order_action_fixtures import ActionFixtures
from tokens.tests.order_submission_fixtures import pending_submission
from users.models.investor_classification import InvestorClassification


def _classification_payload():

    return {
        "user_account": "{account}",
        "category": "product_value",
        "declaration_accepted": True,
        "declared_basis": "Holdings above the threshold.",
        "evidence_file": SimpleUploadedFile("evidence.pdf", pdf_bytes(), content_type="application/pdf"),
    }


def _clear_open_classifications(tenant):
    InvestorClassification.objects.filter(user_account=tenant.account).delete()


SIGNATURE = "0x" + "ab" * 65
DIGEST = "0x" + "cd" * 32
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


def _company_without_a_register(tenant):
    company = Company.objects.create(
        owner=tenant.user,
        name=f"{tenant.label} empty registration",
        acn=an_acn(70000000 + tenant.user.pk),
        company_type=tenant.company.company_type,
        operator_wallet=tenant.wallet,
    )
    return {"company": str(company.pk)}


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


def _an_issuance_request(tenant):
    return _create_issuance_request(
        tenant.deployed_token, "0x" + "c" * 40, 10, tenant.user, reason="Founder allocation"
    )


def _a_pending_order_submission(tenant):
    pending_submission(tenant, submission_id=tenant.account.pk)


Route = namedtuple(
    "Route",
    "method path payload foreign prepare rejects content_type",
    defaults=(None, 404, None, None, "json"),
)

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
        "post",
        "/api/wallets/batch-check-balances/",
        {"userAccount": "{account}", "chain": "base", "addresses": [NEW_WALLET_ADDRESS]},
    ),
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
    Route("delete", "/api/v1/companies/{company}/", prepare=_company_without_a_register),
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
    Route("get", "/api/v1/tokens/issuance-requests/{issuance_request}/"),
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
    Route(
        "post",
        "/api/portfolios/",
        {"name": "A portfolio", "userAccount": "{account}"},
        foreign=400,
        rejects="userAccount",
    ),
    Route(
        "post",
        "/api/favourite-assets/",
        {"userAccount": "{account}", "asset": "{stablecoin}"},
        foreign=400,
        rejects="userAccount",
    ),
    Route(
        "post",
        "/api/user-preferences/",
        {"selectedAccount": "{account}"},
        foreign=400,
        rejects="selectedAccount",
    ),
    Route(
        "post",
        "/api/investor-classifications/",
        _classification_payload,
        foreign=400,
        rejects="userAccount",
        content_type="multipart",
        prepare=_clear_open_classifications,
    ),
    Route(
        "get",
        "/api/v1/trading/swaps/?wallet_address={wallet_address}",
    ),
    Route(
        "get",
        "/api/v1/trading/wallets/balances/?wallet_address={wallet_address}",
    ),
    Route(
        "post",
        "/api/v1/trading/transfers/prepare/",
        {
            "token": "{own_deployed_token}",
            "fromAddress": "{wallet_address}",
            "toAddress": RECIPIENT,
            "amount": 1,
        },
    ),
    Route(
        "post",
        "/api/v1/trading/orders/create/",
        {
            "submissionId": "{own_account}",
            "ownerAccountUuid": "{own_account}",
            "token": "{own_deployed_token}",
            "orderType": "sell",
            "walletUuid": "{wallet}",
            "walletAddress": "{own_wallet_address}",
            "quantity": 1,
            "pricePerShare": "2.50",
            "digest": DIGEST,
            "signature": SIGNATURE,
        },
        foreign=400,
        rejects="walletUuid",
    ),
    Route(
        "post",
        "/api/v1/trading/orders/create/message/",
        {
            "submissionId": "{own_account}",
            "ownerAccountUuid": "{own_account}",
            "token": "{own_deployed_token}",
            "orderType": "sell",
            "walletUuid": "{wallet}",
            "walletAddress": "{own_wallet_address}",
            "quantity": 1,
            "pricePerShare": "2.50",
        },
        foreign=400,
        rejects="walletUuid",
    ),
    Route(
        "get",
        "/api/v1/trading/orders/submissions/{account}/?owner_account_uuid={account}",
        prepare=_a_pending_order_submission,
    ),
    Route("get", "/api/v1/trading/orders/{order}/"),
    Route("get", "/api/v1/trading/orders/{order}/modifications/"),
    Route(
        "get",
        "/api/v1/trading/orders/{order}/swap/?swap_uuid={swap}"
        "&owner_account_uuid={own_account}&wallet_uuid={own_wallet}",
    ),
    Route(
        "post",
        "/api/v1/trading/orders/{order}/swap/sign/",
        {
            "signature": SIGNATURE,
            "signerAddress": "{own_wallet_address}",
            "swapUuid": "{swap}",
            "ownerAccountUuid": "{own_account}",
            "walletUuid": "{own_wallet}",
            "settlementDigest": "{own_settlement_digest}",
        },
    ),
    Route(
        "get",
        "/api/v1/trading/orders/{order}/swap/approval-status/?swap_uuid={swap}"
        "&owner_account_uuid={own_account}&wallet_uuid={own_wallet}&settlement_digest={own_settlement_digest}",
    ),
    Route(
        "get",
        "/api/v1/trading/orders/{order}/swap/approval-data/?swap_uuid={swap}"
        "&owner_account_uuid={own_account}&wallet_uuid={own_wallet}&settlement_digest={own_settlement_digest}",
    ),
    Route(
        "post",
        "/api/v1/trading/orders/{order}/swap/approval-broadcast/",
        {
            "swapUuid": "{swap}",
            "ownerAccountUuid": "{own_account}",
            "walletUuid": "{own_wallet}",
            "settlementDigest": "{own_settlement_digest}",
            "signedTransaction": "0xab",
        },
    ),
    Route("get", "/api/v1/documents/{document}/"),
    Route("get", "/api/v1/documents/{document}/file/"),
    Route("post", "/api/v1/documents/{document}/attach/", {"classification": "{own_investor_classification}"}),
    Route("post", "/api/v1/documents/{own_document}/attach/", {"classification": "{investor_classification}"}),
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

REGISTRY_ADMIN_ROUTES = (
    ("start-review", CompanyStatus.SUBMITTED, CompanyStatus.REVIEW),
    ("retry-registry", CompanyStatus.REVIEW, CompanyStatus.REVIEW),
    ("approve", CompanyStatus.REVIEW, CompanyStatus.APPROVED),
    ("activate", CompanyStatus.APPROVED, CompanyStatus.APPROVED),
    ("resolve-warning", CompanyStatus.WARNING, CompanyStatus.WARNING),
    ("reinstate", CompanyStatus.SUSPENDED, CompanyStatus.SUSPENDED),
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
    ("/api/v1/tokens/issuance-requests/", ("issuance_request",)),
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
    if callable(value):
        return _fill(value(), context)
    if isinstance(value, str):
        return value.format_map(context)
    if isinstance(value, dict):
        return {key: _fill(item, context) for key, item in value.items()}
    return value


class CrossTenantRouteMatrixTest(StubUploadDependencies, APITransactionTestCase):

    @staticmethod
    def routes():
        return ROUTES

    @contextmanager
    def undone_before_the_next_case(self):
        with atomic():
            yield
            transaction.set_rollback(True, using=current_alias())

    @contextmanager
    def as_an_operator_would(self):
        yield

    @contextmanager
    def committed_where_a_request_on_another_connection_can_read_it(self):
        with self.as_an_operator_would():
            yield

    @contextmanager
    def as_whoever_may_write_the_fixture(self, route, context, owner, actor):
        yield

    def setUp(self):
        FeatureFlag.objects.update_or_create(name="trading_enabled", defaults={"enabled": True})
        self._patch("rest_framework.throttling.SimpleRateThrottle.allow_request", return_value=True)
        self.services = []
        self._service("wallets.views.wallet.sync_wallet", return_value={"status": "success"})
        wallet_transfer = self._service("wallets.views.wallet.transfers")
        wallet_transfer.prepare_transfer.return_value = {"transaction": {}}
        wallet_transfer.broadcast_transfer.return_value = {"success": True}
        self._service("wallets.services.balance.get_blockchain_client").return_value.get_native_balance.return_value = (
            Decimal("0")
        )
        self._service("wallets.services.verification.verify_wallet_signature", return_value=True)
        self._service("wallets.tasks.sync_wallet").defer.return_value = "job"
        self._service("wallets.views.fiat_purchase.generate_transak_widget_url", return_value="https://widget.test")
        self._service("companies.services.company.send_push_notification")
        self._service("offerings.services.offering.send_push_notification")
        self._service("tokens.tasks.deploy_share_token_task")
        share_tokens = self._service("tokens.views.share_token.ShareTokenService")
        share_tokens.create_issuance_request.side_effect = _create_issuance_request
        balances_need_a_readable_chain = self._service("tokens.views.trading_wallet.ShareTokenService").return_value
        balances_need_a_readable_chain.get_wallet_token_balances.return_value = {"balances": []}
        register_chain = self._service("tokens.services.register.ShareTokenService").return_value
        register_chain.deployment_block.return_value = 1
        register_chain.transfer_participants.return_value = set()
        register_chain.get_token_balance.return_value = 0
        register_chain.share_supply.return_value = (0, 0)
        self._service("tokens.views.trading_order.execute_order_submission")
        self._service("tokens.views.trading_order.issue_order_submission")
        self._service("tokens.views.trading_order.submission_snapshot").return_value = {}
        trading_transfers = self._service("tokens.views.trading_transfer.TokenTransferService")
        trading_transfers.contract_address.return_value = "0x" + "6" * 40
        trading_transfers.return_value.prepare_transfer.return_value = {}
        self._service("tokens.views.trading_order.get_modification_history").return_value = {}
        swaps = self._service("tokens.views.trading_order.AtomicSwapService").return_value
        swaps.contract_address = SYNTHETIC_SETTLEMENT_CONTRACT
        swaps.settlement_contract.return_value = SYNTHETIC_SETTLEMENT_CONTRACT
        swaps.broadcast_settlement_approval.return_value = ("0x" + "ab" * 32, {"blockNumber": 1, "gasUsed": 21000})
        self.enterContext(override_settings(ATOMIC_SWAP_ADDRESS=SYNTHETIC_SETTLEMENT_CONTRACT))
        swaps.find_swap_order_by_transfer_order.side_effect = SwapOrder.objects.for_transfer_order
        swaps.submit_signature.side_effect = lambda swap_order, **kwargs: swap_order
        swaps.get_typed_data.return_value = {}
        swaps.check_swap_allowances.return_value = {"seller": ALLOWANCE, "buyer": ALLOWANCE}
        swaps.get_approval_transaction_data.return_value = {}

        self.actors = (make_tenant("alice"), make_tenant("staff", staff=True), make_tenant("root", superuser=True))
        self.other = make_tenant("bob")
        for tenant in (*self.actors, self.other):
            tenant.issuance_request = _an_issuance_request(tenant)

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
        return self.perform(route, context)

    def perform(self, route, context):
        request = getattr(self.client, route.method)
        return request(route.path.format_map(context), _fill(route.payload, context), format=route.content_type)

    def assert_rejected_for_the_right_reason(self, route, response, label):
        if not route.rejects:
            return
        body = response.json()
        self.assertIn(
            route.rejects,
            body,
            f"{label} answered {response.status_code} without naming {route.rejects}: {body}",
        )

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
        with self.as_an_operator_would():
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
                    self.assert_rejected_for_the_right_reason(route, foreign_response, "foreign")
                    self.assert_rejected_for_the_right_reason(route, phantom_response, "phantom")

        with self.as_an_operator_would():
            self.assertEqual(snapshot(self.other), before)
        for service in self.services:
            self.assertEqual(service.mock_calls, [])

    def test_own_rows_resolve_for_every_actor(self):
        for actor in self.actors:
            self.client.force_authenticate(actor.user)
            own = route_context(actor)
            for route in ROUTES:
                with self.subTest(actor=actor.label, route=f"{route.method} {route.path}"):

                    with self.undone_before_the_next_case():
                        context = dict(own)
                        if route.prepare:
                            with self.as_whoever_may_write_the_fixture(route, own, actor, actor):
                                prepared = route.prepare(actor)
                                if isinstance(prepared, dict):
                                    context.update(prepared)
                        response = self.send(route, actor, context)
                    self.assertIn(response.status_code, (200, 201, 202, 204), _body(response))

    def test_operator_routes_are_staff_only_and_reach_every_tenant(self):
        foreign = route_context(self.other)
        phantom = phantom_context(self.other)
        for actor in self.actors:
            self.client.force_authenticate(actor.user)
            for route in OPERATOR_ROUTES:
                with self.subTest(actor=actor.label, route=f"{route.method} {route.path}"):
                    with self.undone_before_the_next_case():
                        if route.prepare:
                            with self.as_whoever_may_write_the_fixture(route, foreign, self.other, actor):
                                route.prepare(self.other)
                        foreign_response = self.send(route, actor, foreign)
                        phantom_response = self.send(route, actor, phantom)
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
                    with self.undone_before_the_next_case():
                        with self.as_whoever_may_write_the_fixture(route, foreign, actor, actor):
                            make_eligible(actor)
                        with self.as_whoever_may_write_the_fixture(route, foreign, self.other, actor):
                            open_to_investors(self.other)
                        foreign_response = self.send(route, actor, foreign)
                        phantom_response = self.send(route, actor, phantom)
                    self.assertEqual(foreign_response.status_code, 200, foreign_response.content)
                    self.assertEqual(phantom_response.status_code, 404, phantom_response.content)

    def test_the_market_answers_without_the_issuers_directory_opt_in(self):
        foreign = route_context(self.other)
        for actor in self.actors:
            self.client.force_authenticate(actor.user)
            for route in MARKET_ROUTES + DIRECTORY_ROUTES:
                with self.subTest(actor=actor.label, route=f"{route.method} {route.path}"):
                    with self.undone_before_the_next_case():
                        with self.as_whoever_may_write_the_fixture(route, foreign, actor, actor):
                            make_eligible(actor)
                        foreign_response = self.send(route, actor, foreign)
                    expected = 200 if route in MARKET_ROUTES else 404
                    self.assertEqual(foreign_response.status_code, expected, foreign_response.content)

    def test_directory_and_market_routes_are_empty_and_not_found_without_eligibility(self):
        foreign = route_context(self.other)
        phantom = phantom_context(self.other)
        for actor in self.actors:
            self.client.force_authenticate(actor.user)
            for route in DIRECTORY_ROUTES + MARKET_ROUTES:
                with self.subTest(actor=actor.label, route=f"{route.method} {route.path}"):
                    with self.undone_before_the_next_case():
                        with self.as_whoever_may_write_the_fixture(route, foreign, self.other, actor):
                            open_to_investors(self.other)
                        foreign_response = self.send(route, actor, foreign)
                        phantom_response = self.send(route, actor, phantom)
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

        with self.committed_where_a_request_on_another_connection_can_read_it():
            make_eligible(alice)
        self.assertEqual(self.client.get(GLOBAL_ROUTES[0]).json()["paymentInstructions"], RAILS)

    @override_settings(
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
        }
    )
    def test_registry_admin_actions_refuse_tenant_and_unprivileged_staff_and_admit_the_operator(self):
        self.client.force_authenticate(None)
        with patch(
            "companies.services.registry.lookup_company", return_value=RegistryObservation(reason="unconfigured")
        ) as provider:
            for actor, expected in zip(self.actors, (302, 403, 200)):
                self.client.force_login(actor.user)
                for action, predecessor, successor in REGISTRY_ADMIN_ROUTES:
                    with self.subTest(actor=actor.label, action=action):
                        with self.as_an_operator_would():
                            Company.objects.filter(pk=self.other.company.pk).update(status=predecessor)
                            before = CompanyRegistryCheck.objects.count()
                        path = reverse("admin:companies_company_transition", args=[self.other.company.pk, action])
                        page = self.client.get(path)
                        self.assertEqual(page.status_code, expected)
                        with self.as_an_operator_would():
                            self.assertEqual(Company.objects.get(pk=self.other.company.pk).status, predecessor)
                            self.assertEqual(CompanyRegistryCheck.objects.count(), before)
                        response = self.client.post(path, {"confirm": True, **DECLARATION})
                        self.assertEqual(response.status_code, 302 if expected == 200 else expected)
                        with self.as_an_operator_would():
                            current = Company.objects.get(pk=self.other.company.pk)
                            self.assertEqual(current.status, successor if expected == 200 else predecessor)
                            if expected == 200 and action != "approve":
                                self.assertEqual(CompanyRegistryCheck.objects.count(), before + 1)
                            else:
                                self.assertEqual(CompanyRegistryCheck.objects.count(), before)
                self.client.logout()
            self.assertEqual(provider.call_count, len(REGISTRY_ADMIN_ROUTES) - 1)


ACTION_ROUTES = (
    Route("get", "/api/v1/trading/orders/{order}/action-context/?owner_account_uuid={account}"),
    Route("get", "/api/v1/trading/orders/actions/{action}/?owner_account_uuid={account}"),
    Route("post", "/api/v1/trading/orders/{order}/cancel/message/"),
    Route("post", "/api/v1/trading/orders/{order}/modify/message/"),
    Route("post", "/api/v1/trading/orders/{order}/cancel/"),
    Route("post", "/api/v1/trading/orders/{order}/modify/"),
    Route("get", "/api/v1/trading/orders/{order}/cancel/message/", foreign=400),
)


class OrderActionRouteChecks(ActionFixtures):
    def setUp(self):
        super().setUp()
        self.cancel_order = self.order
        self.cancel_signed = self.signed()
        with use_operator():
            self.order = TransferOrder.objects.create(
                token=self.order.token,
                payment_asset=self.order.payment_asset,
                wallet=self.wallet,
                owner_account=self.tenant.account,
                wallet_address=self.wallet.address,
                order_type="buy",
                quantity=10,
                price_per_share=Decimal("2.50"),
            )
            self.other = make_tenant("action-matrix-other")
        self.action_id = uuid4()
        self.modify_signed = self.signed("modify", self.modify_body())

    def request_route(self, route, missing=False):
        modify = "/modify" in route.path
        signed = self.modify_signed if modify else self.cancel_signed
        order = self.order if modify else self.cancel_order
        context = {
            "order": str(uuid4() if missing else order.pk),
            "account": str(self.tenant.account.pk),
            "action": str(uuid4() if missing else signed["action_id"]),
        }
        body = {**signed, "action_id": context["action"]}
        if modify and "/message/" in route.path:
            body = {**self.modify_body(), **body}
        return getattr(self.client, route.method)(
            route.path.format_map(context), body if route.method == "post" else None, format="json"
        )

    def test_owned_action_routes_reach_the_real_service_and_preserve_legacy_refusal(self):
        for route in ACTION_ROUTES:
            with self.subTest(method=route.method, path=route.path):
                response = self.request_route(route)
                expected = 400 if route.foreign == 400 else 200
                self.assertEqual(response.status_code, expected, response.content)
                if expected == 400:
                    self.assertEqual(response.json()["code"], "action_refresh_required")
        self.assertEqual([event for event, _ in self.events], ["order_cancelled", "order_modified"])

    def test_foreign_and_missing_actions_stay_hidden_for_regular_staff_and_superusers(self):
        for staff, superuser in ((False, False), (True, False), (True, True)):
            with use_operator():
                self.other.user.is_staff = staff
                self.other.user.is_superuser = superuser
                self.other.user.save(update_fields=["is_staff", "is_superuser"])
            self.client.force_authenticate(self.other.user)
            for route in ACTION_ROUTES:
                with self.subTest(staff=staff, superuser=superuser, path=route.path, method=route.method):
                    foreign = self.request_route(route)
                    missing = self.request_route(route, missing=True)
                    self.assertEqual(foreign.status_code, route.foreign, foreign.content)
                    self.assertEqual(missing.status_code, route.foreign, missing.content)
                    self.assertEqual(foreign.json(), missing.json())
        self.assert_pending(self.cancel_signed)
        self.assert_pending(self.modify_signed)
        self.client.force_authenticate(self.tenant.user)
        for signed, purpose, order in (
            (self.cancel_signed, "cancel", self.cancel_order),
            (self.modify_signed, "modify", self.order),
        ):
            self.assertEqual(self.execute(purpose, signed, order).status_code, 200)

    def test_all_action_routes_refuse_anonymous_and_recover_after_authentication(self):
        self.client.force_authenticate(None)
        for route in ACTION_ROUTES:
            with self.subTest(method=route.method, path=route.path):
                response = self.request_route(route)
                self.assertEqual(response.status_code, 401, response.content)
        self.client.force_authenticate(self.tenant.user)
        self.assertEqual(self.context().status_code, 200)
        self.assertEqual(self.recover().status_code, 200)


class OrderActionRouteMatrixTest(OrderActionRouteChecks, APITransactionTestCase):
    pass


class ScopedOrderActionRouteMatrixTest(RunsOnTheScopedConnection, OrderActionRouteChecks, APITransactionTestCase):
    pass
