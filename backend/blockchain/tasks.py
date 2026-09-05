from typing import Any

from procrastinate import RetryStrategy

from ledova_backend.procrastinate_app import app


@app.periodic(cron="*/5 * * * *")
@app.task(retry=RetryStrategy(max_attempts=4, wait=60))
def check_pending_transactions(timestamp: int) -> dict[str, Any]:
    from blockchain.services import TransactionMonitorService
    from integrations.base_chain import get_base_chain_client

    chain_client = get_base_chain_client()
    return TransactionMonitorService.check_pending_transactions(chain_client)


@app.periodic(cron="0 3 * * *")
@app.task(retry=RetryStrategy(max_attempts=4, wait=60))
def cleanup_failed_transactions(timestamp: int) -> dict[str, Any]:
    from blockchain.services import TransactionMonitorService

    return TransactionMonitorService.cleanup_stale_transactions(hours=24)
