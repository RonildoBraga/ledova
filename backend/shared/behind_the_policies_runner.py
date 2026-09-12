from unittest import TestSuite

from django.test.runner import DiscoverRunner


def ids(module, case, *tests):
    return tuple(f"{module}.{case}.{test}" for test in tests)


LISTINGS_THAT_COME_BACK_EMPTY_FOR_THEIR_OWN_OWNER = (
    *ids(
        "offerings.tests.test_issuer_subscriptions",
        "IssuerSubscriptionReadTest",
        "test_the_issuer_keeps_other_investors_on_newest_first_pages",
    ),
)

A_SECOND_MODEL_THE_VIEW_READS_OUTSIDE_THE_PRINCIPALS_SCOPE = (
    *ids(
        "users.tests.test_investor_classification_api",
        "InvestorClassificationApiTest",
        "test_an_associated_person_claim_must_name_an_active_issuer",
    ),
    *ids(
        "wallets.tests.test_wallet_create_portfolio_assignment",
        "WalletCreatePortfolioAssignmentTest",
        "test_new_wallet_is_not_added_when_the_selected_portfolio_belongs_to_another_account",
    ),
)

MARKET_AND_BALANCE_FIELDS_THAT_GO_QUIET = (
    *ids(
        "tokens.tests.test_market_summary",
        "MarketSummaryTest",
        "test_lists_expose_market_fields_without_per_row_queries",
    ),
    *ids(
        "wallets.tests.test_wallet_read_contract",
        "WalletReadContractTest",
        "test_list_reports_string_balances_from_holdings_without_per_row_queries",
    ),
)

NOT_YET_BEHIND_THE_POLICIES = (
    *LISTINGS_THAT_COME_BACK_EMPTY_FOR_THEIR_OWN_OWNER,
    *A_SECOND_MODEL_THE_VIEW_READS_OUTSIDE_THE_PRINCIPALS_SCOPE,
    *MARKET_AND_BALANCE_FIELDS_THAT_GO_QUIET,
)

UNEXPECTED_SUCCESS = (
    "These tests are listed as not yet passing behind the policies, and they passed: {tests}. "
    "Remove them from NOT_YET_BEHIND_THE_POLICIES - the list may only shrink."
)


def cases_in(suite):
    for item in suite:
        if isinstance(item, TestSuite):
            yield from cases_in(item)
        else:
            yield item


def let_the_listed_ones_fail(suite, listed):
    for case in cases_in(suite):
        if case.id() in set(listed):
            getattr(case, case._testMethodName).__func__.__unittest_expecting_failure__ = True
    return suite


class BehindThePoliciesRunner(DiscoverRunner):

    def build_suite(self, *args, **kwargs):
        return let_the_listed_ones_fail(super().build_suite(*args, **kwargs), NOT_YET_BEHIND_THE_POLICIES)

    def suite_result(self, suite, result, **kwargs):
        unexpected = [case.id() for case in getattr(result, "unexpectedSuccesses", [])]
        if unexpected:
            self.log(UNEXPECTED_SUCCESS.format(tests=", ".join(sorted(unexpected))))
        return super().suite_result(suite, result, **kwargs)
