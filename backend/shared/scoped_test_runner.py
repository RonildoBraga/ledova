import ast
from unittest import TestLoader, TestSuite

from django.conf import settings
from django.core.management.base import CommandError
from django.test.runner import DiscoverRunner

from shared.db import APP_ALIAS, MIGRATE_ALIAS, OPERATOR_ALIAS

SCOPED_TEST_LABELS = (
    "shared.tests.test_scoped_harness.TheScopedHarnessIsActuallyScopedTest",
    "shared.tests.test_scoped_harness.ADecoratedServiceRollsBackOnTheConnectionItRanOnTest",
    "users.tests.test_account_type_under_the_app_role.ChoosingAnAccountTypeUnderTheAppRoleTest",
    "shared.tests.test_cross_tenant_routes_under_rls.TheMatrixRunsOnTheConnectionTheRouterChoosesTest",
    "shared.tests.test_scoped_requests.AuthRequestsUseTheAppRoleTest",
    "shared.tests.test_scoped_requests.RequestTransactionsUseTheAppRoleTest",
    "shared.tests.test_scoped_requests.LockedUpdatesUseTheAppRoleTest",
    "wallets.tests.test_confirmation_under_split_roles.ConfirmationUsesSeparateRolesTest",
    "tokens.tests.test_modification_refusals.ScopedModificationRefusalTest",
    "tokens.tests.test_order_submissions.ScopedOrderSubmissionRecoveryTest",
    "tokens.tests.test_order_submission_processes.ScopedOrderSubmissionProcessTest",
    "tokens.tests.test_matching_wallet_locks.ScopedMatchingWalletLockTest",
    "wallets.tests.test_confirmation_locking.ScopedConfirmationLockingTest",
    "wallets.tests.test_history_preservation.ScopedHistoryPreservationTest",
    "tokens.tests.test_former_member_privacy.ScopedFormerMemberPrivacyTest",
    "documents.tests.test_evidence_under_scoped_roles.ScopedSupportingEvidenceTest",
    "wallets.tests.test_network_identity.ScopedWalletNetworkIdentityTest",
    "companies.tests.test_registry_policy.ReviewedCompanyDeletionOnScopedConnectionTest",
    "blockchain.tests.test_monitor_scoped.ScopedMonitorObservationsTest",
)


def cases_in(suite):
    for item in suite:
        if isinstance(item, TestSuite):
            yield from cases_in(item)
        else:
            yield item


def declared_scoped_classes():
    labels = set()
    for path in settings.BASE_DIR.glob("*/tests/test*.py"):
        module = ".".join(path.relative_to(settings.BASE_DIR).with_suffix("").parts)
        for node in ast.parse(path.read_text()).body:
            if isinstance(node, ast.ClassDef) and any(
                getattr(base, "id", getattr(base, "attr", None)) == "RunsOnTheScopedConnection" for base in node.bases
            ):
                labels.add(f"{module}.{node.name}")
    return labels


class ScopedTestRunner(DiscoverRunner):
    @classmethod
    def add_arguments(cls, parser):
        super().add_arguments(parser)
        parser.add_argument("--require-scoped-coverage", action="store_true")

    def __init__(self, *args, require_scoped_coverage=False, **kwargs):
        self.require_scoped_coverage = require_scoped_coverage
        super().__init__(*args, **kwargs)

    def build_suite(self, test_labels=None, **kwargs):
        suite = super().build_suite(test_labels or SCOPED_TEST_LABELS, **kwargs)
        if self.require_scoped_coverage:
            if settings.RLS_AMBIENT_ALIAS != APP_ALIAS or not {APP_ALIAS, MIGRATE_ALIAS, OPERATOR_ALIAS} <= set(
                settings.DATABASES
            ):
                raise CommandError("The scoped suite requires the app ambient alias and all three database connections")
            difference = declared_scoped_classes() ^ set(SCOPED_TEST_LABELS)
            if difference:
                raise CommandError(f"The scoped class inventory and required labels differ: {sorted(difference)}")
            expected = list(cases_in(TestLoader().loadTestsFromNames(SCOPED_TEST_LABELS)))
            present = {case.id() for case in cases_in(suite)}
            missing = {case.id() for case in expected} - present
            empty = {
                label for label in SCOPED_TEST_LABELS if not any(case.id().startswith(label + ".") for case in expected)
            }
            if missing or empty:
                raise CommandError(f"Required scoped tests are missing: {sorted(missing | empty)}")
            skipped = [case.id() for case in expected if getattr(case, "__unittest_skip__", False)]
            if skipped:
                raise CommandError(f"Required scoped tests are marked skipped: {skipped}")
        return suite

    def run_suite(self, suite, **kwargs):
        result = super().run_suite(suite, **kwargs)
        if self.require_scoped_coverage and result.skipped:
            raise CommandError(f"The required scoped suite skipped {len(result.skipped)} test(s)")
        return result
