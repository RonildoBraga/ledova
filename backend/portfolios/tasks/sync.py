import logging
from typing import Any, Dict

from ledova_backend.procrastinate_app import app
from portfolios.models.portfolio import Portfolio
from portfolios.services.sync import PortfolioSyncService
from shared.utils.logging_utils import LoggingContext

logger = logging.getLogger("ledova_backend")


@app.periodic(cron="0 21 * * *")
@app.task
def sync_all_portfolios(timestamp: int) -> Dict[str, Any]:
    """Snapshot every active portfolio. Runs daily at 21:00 UTC."""
    logger.info(f"{LoggingContext.PORTFOLIOS} Starting portfolio sync")

    portfolios = Portfolio.objects.filter(is_active=True)

    total_created = 0
    total_errors = 0
    results = []

    for portfolio in portfolios:
        try:
            result = PortfolioSyncService.sync_portfolio(portfolio=portfolio)

            if result["status"] == "success":
                total_created += result.get("snapshots_created", 0)
                results.append(
                    {
                        "portfolio": portfolio.name,
                        "status": "success",
                        "created": result.get("snapshots_created", 0),
                    }
                )
            else:
                total_errors += 1
                results.append({"portfolio": portfolio.name, "status": "error", "error": result.get("error")})

        except Exception as e:
            total_errors += 1
            logger.error(f"{LoggingContext.PORTFOLIOS} Failed to sync portfolio {portfolio.name}: {e}")
            results.append({"portfolio": portfolio.name, "status": "error", "error": str(e)})

    logger.info(
        f"{LoggingContext.PORTFOLIOS} Portfolio sync completed - Created: {total_created}, Errors: {total_errors}"
    )

    return {"created": total_created, "errors": total_errors, "results": results}
