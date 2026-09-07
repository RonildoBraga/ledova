from tokens.models.share_issuance import ShareIssuance


def dilution_for(request) -> float:
    return request.dilution_against(ShareIssuance.objects.completed_supply(request.token))
