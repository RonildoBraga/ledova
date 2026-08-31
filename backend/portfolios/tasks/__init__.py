"""
Tasks package for portfolios app.
"""

from portfolios.tasks.sync import sync_all_portfolios

__all__ = [
    "sync_all_portfolios",
]
