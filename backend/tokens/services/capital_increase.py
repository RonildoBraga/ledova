from shared.db import atomic
from tokens.exceptions import InvalidTokenStateException
from tokens.models import CapitalIncreaseRequest, ShareToken
from tokens.services.dilution import dilution_for

ALREADY_IN_FLIGHT = (
    "{symbol} already has a capital increase in flight ({status}, requested {requested}). "
    "One share class raises its cap once at a time, so wait for that one to finish, or ask the operator to reject it."
)


@atomic()
def submit_capital_increase(capital_increase: CapitalIncreaseRequest, user) -> CapitalIncreaseRequest:
    ShareToken.objects.select_for_update().get(pk=capital_increase.token_id)
    capital_increase.refresh_from_db()
    in_flight = (
        CapitalIncreaseRequest.objects.filter(token=capital_increase.token)
        .exclude(pk=capital_increase.pk)
        .in_flight()
        .order_by("created_at")
        .first()
    )
    if in_flight is not None:
        raise InvalidTokenStateException(
            ALREADY_IN_FLIGHT.format(
                symbol=capital_increase.token.symbol,
                status=in_flight.get_status_display(),
                requested=in_flight.created_at.date().isoformat(),
            )
        )

    capital_increase.submit(user, dilution_for(capital_increase))

    return capital_increase
