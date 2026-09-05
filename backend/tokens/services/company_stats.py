from tokens.models import CapitalIncreaseRequest, ShareIssuance, ShareToken


def company_stats(company) -> dict:
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
