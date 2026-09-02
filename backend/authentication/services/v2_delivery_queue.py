import uuid

from django.db import transaction
from procrastinate.contrib.django.django_connector import DjangoConnector

from authentication.tasks import V2_DELIVERY_HOLD_QUEUE, deliver_v2_challenge
from ledova_backend.logging_filters import V2_DELIVERY_TASK_NAME
from ledova_backend.procrastinate_app import app

_QUEUE_ERROR = "V2 challenge queue unavailable."


class _V2DeliveryQueueError(RuntimeError):
    pass


def _raise_queue_error():
    raise _V2DeliveryQueueError(_QUEUE_ERROR) from None


def _validate_v2_delivery_queue(*, selected, raw_connection):
    failed = False
    try:
        connector = app.connector
        registered = app.tasks.get(V2_DELIVERY_TASK_NAME)
        task_connector = registered.blueprint.job_manager.connector if registered is not None else None
        valid = (
            type(connector) is DjangoConnector
            and task_connector is connector
            and connector.alias == selected.alias
            and connector.connection is selected
            and selected.connection is raw_connection
            and raw_connection is not None
            and selected.queries_logged is False
            and selected.in_atomic_block is True
            and selected.get_autocommit() is False
            and transaction.get_rollback(using=selected.alias) is False
            and registered is deliver_v2_challenge
            and registered.name == V2_DELIVERY_TASK_NAME
            and registered.queue == V2_DELIVERY_HOLD_QUEUE
            and registered.retry_strategy is None
            and registered.lock is None
            and registered.queueing_lock is None
        )
        if not valid:
            raise ValueError
    except Exception:
        failed = True

    if failed:
        _raise_queue_error()


def _enqueue_reserved_v2_delivery(*, selected, raw_connection, delivery_id):
    failed = False
    try:
        _validate_v2_delivery_queue(selected=selected, raw_connection=raw_connection)
        if type(delivery_id) is not uuid.UUID or delivery_id.version != 4:
            raise ValueError
        job_id = deliver_v2_challenge.defer(delivery_uuid=str(delivery_id))
        _validate_v2_delivery_queue(selected=selected, raw_connection=raw_connection)
        if type(job_id) is not int or job_id <= 0:
            raise ValueError
        return job_id
    except Exception:
        failed = True

    if failed:
        _raise_queue_error()
