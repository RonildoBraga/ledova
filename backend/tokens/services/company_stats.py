from tokens.models import CapitalIncreaseRequest, ShareIssuance, ShareToken


def company_stats(company) -> dict:
    deployed = ShareToken.objects.filter(company=company).deployed()
    pending = CapitalIncreaseRequest.objects.filter(token__company=company).pending().count()
    return {
        "totalTokens": deployed.count(),
        "totalShareholders": ShareIssuance.objects.filter(token__in=deployed).distinct_recipient_addresses().count(),
        "pendingActions": pending,
        "pendingCapitalIncreases": pending,
    }
