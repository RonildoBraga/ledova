"""
Views package for portfolios app.
"""

from portfolios.views.asset_allocation import AssetAllocationViewSet
from portfolios.views.portfolio import PortfolioViewSet

__all__ = [
    "AssetAllocationViewSet",
    "PortfolioViewSet",
]
