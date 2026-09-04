from tokens.models import CapitalIncreaseRequest, ShareIssuance, ShareToken


def company_stats(company) -> dict:
    """The company page counters; the camelCase keys are read by the dashboard and mobile app."""
    deployed = ShareToken.objects.filter(company=company).deployed()
    pending = CapitalIncreaseRequest.objects.filter(token__company=company).pending().count()
    shareholders = (
        ShareIssuance.objects.completed().filter(token__in=deployed).values("recipient_address").distinct().count()
    )
    return {
        "totalTokens": deployed.count(),
        "totalShareholders": shareholders,
        "pendingActions": pending,
        "pendingCapitalIncreases": pending,
    }
