from tokens.models import CapitalIncreaseRequest
from tokens.services.dilution import dilution_for


def submit_capital_increase(capital_increase: CapitalIncreaseRequest, user) -> CapitalIncreaseRequest:
    capital_increase.submit(user, dilution_for(capital_increase))

    return capital_increase
