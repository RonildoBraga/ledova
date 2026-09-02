from ledova_backend.logging_filters import V2_DELIVERY_TASK_NAME
from ledova_backend.procrastinate_app import app

V2_DELIVERY_HOLD_QUEUE = "v2_challenge_hold"
_V2_DELIVERY_UNAVAILABLE = "V2 challenge delivery worker unavailable."


@app.task(name=V2_DELIVERY_TASK_NAME, queue=V2_DELIVERY_HOLD_QUEUE, retry=False)
def deliver_v2_challenge(*, delivery_uuid: str) -> None:
    raise RuntimeError(_V2_DELIVERY_UNAVAILABLE) from None
