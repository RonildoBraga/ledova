"""
Admin package for portfolios app.
Imports all admin classes to register them with Django admin.
"""

from portfolios.admin.portfolio import (
    AssetAllocationAdmin,
    PortfolioAdmin,
)

__all__ = [
    "AssetAllocationAdmin",
    "PortfolioAdmin",
]
