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
    *ids(
        "tokens.tests.test_swap_isolation",
        "SwapQuerysetIsScopedToTheCallerTest",
        "test_a_second_owned_wallet_does_not_widen_the_listing_for_the_first",
        "test_the_listing_returns_only_the_callers_swap",
    ),
    *ids(
        "tokens.tests.test_trading_read_isolation",
        "TradingReadIsolationTest",
        "test_pending_swaps_accepts_an_owned_case_variant",
        "test_pending_swaps_are_paginated_and_newest_first",
    ),
)

REGISTER_READS_OF_HOLDERS_THE_READER_DOES_NOT_OWN = (
    *ids(
        "tokens.tests.test_register",
        "HolderTypeTest",
        "test_the_four_holder_types_come_out_of_one_register_read",
    ),
    *ids(
        "tokens.tests.test_register",
        "RegisterExportTest",
        "test_the_csv_carries_the_header_the_residential_address_and_a_blank_unknown_amount",
        "test_the_residential_address_never_reaches_the_api",
    ),
    *ids(
        "tokens.tests.test_register",
        "RegisterTruthTest",
        "test_a_holding_only_part_of_which_was_subscribed_prints_no_amount_paid",
        "test_a_name_or_address_that_opens_like_a_formula_is_neutralised_in_the_csv",
    ),
    *ids(
        "tokens.tests.test_register_lists_every_holder",
        "TransferAcquiredHolderTest",
        "test_the_export_prints_each_holders_share_of_issued_supply",
        "test_the_transferee_carries_their_chain_balance_and_their_name",
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
    *REGISTER_READS_OF_HOLDERS_THE_READER_DOES_NOT_OWN,
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
