import logging

from ledova_backend.procrastinate_app import app
from shared.services.orphaned_files import sweep_orphaned_files

logger = logging.getLogger(__name__)


@app.periodic(cron="30 3 * * *")
@app.task
def sweep_private_uploads(timestamp: int = 0):
    result = sweep_orphaned_files()
    logger.info(f"Orphaned uploads found: {result['found']}, deleted: {result['deleted']}, failed: {result['failed']}")
    return {"found": result["found"], "deleted": result["deleted"], "failed": result["failed"]}
