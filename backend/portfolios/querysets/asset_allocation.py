from django.db.models import (
    Case,
    DecimalField,
    F,
    Q,
    QuerySet,
    Sum,
    Value,
    When,
)


class AssetAllocationQuerySet(QuerySet):

    def filter_by_portfolio(self, portfolio):
        """Filter by portfolio object. Kept for external callers."""
        if portfolio:
            if portfolio.uuid:
                return self.filter(portfolio__uuid=portfolio.uuid)
        return self

    def filter_active_assets(self):
        return self.filter(asset__is_active=True)

    def exclude_zero_allocations(self):
        return self.filter(percentage__gt=0)

    def visible_to_user(self, user):
        if user.is_superuser or user.is_staff:
            return self
        if not user.is_authenticated:
            return self.none()
        return self.filter(portfolio__user_account__user_profiles__user=user)

    def with_allocation_data(self):
        return self.select_related("portfolio", "asset").filter(asset__is_active=True, percentage__gt=0)

    def with_holdings_data(self, portfolio):
        return self

    def total_allocation_percentage(self):
        result = self.aggregate(total=Sum("percentage"))
        return result["total"] or 0

    def get_allocation_gaps(self, total_portfolio_value, current_holdings_map):
        market_value_cases = []
        for asset_uuid, asset_market_value in current_holdings_map.items():
            market_value_cases.append(
                When(
                    asset__uuid=asset_uuid,
                    then=Value(float(asset_market_value), output_field=DecimalField(max_digits=15, decimal_places=2)),
                )
            )

        if market_value_cases:
            market_value_expression = Case(
                *market_value_cases,
                default=Value(0.0, output_field=DecimalField(max_digits=15, decimal_places=2)),
                output_field=DecimalField(max_digits=15, decimal_places=2),
            )
        else:
            market_value_expression = Value(0.0, output_field=DecimalField(max_digits=15, decimal_places=2))

        return self.annotate(
            target_value=(
                Value(float(total_portfolio_value), output_field=DecimalField(max_digits=15, decimal_places=2))
                * F("percentage")
                / 100
            ),
            market_value=market_value_expression,
            gap_amount=F("target_value") - F("market_value"),
            gap_percentage=(
                F("gap_amount")
                / Value(float(total_portfolio_value), output_field=DecimalField(max_digits=15, decimal_places=2))
                * 100
            ),
        )

    def requiring_adjustment(self, min_adjustment_amount=10.0):
        return self.filter(Q(gap_amount__gt=min_adjustment_amount) | Q(gap_amount__lt=-min_adjustment_amount))

    def for_buying(self, min_adjustment_amount=10.0):
        return self.filter(gap_amount__gt=min_adjustment_amount)

    def for_selling(self, min_adjustment_amount=10.0):
        return self.filter(gap_amount__lt=-min_adjustment_amount)

    def for_allocation_analysis(self, portfolio):
        return (
            self.filter_by_portfolio(portfolio).filter_active_assets().exclude_zero_allocations().with_allocation_data()
        )
