from tokens.models import CapitalIncreaseRequest, ShareToken
from tokens.services.register import register_addresses


def company_stats(company) -> dict:
    deployed = ShareToken.objects.filter(company=company).deployed()
    pending = CapitalIncreaseRequest.objects.filter(token__company=company).pending().count()
    return {
        "totalTokens": deployed.count(),
        "totalShareholders": len(register_addresses(deployed)),
        "pendingActions": pending,
        "pendingCapitalIncreases": pending,
    }
