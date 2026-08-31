"""
Admin package for wallets app.
Imports all admin classes to register them with Django admin.
"""

from wallets.admin.fiat_purchase import FiatTransactionAdmin
from wallets.admin.holding import HoldingAdmin
from wallets.admin.holding_snapshot import HoldingSnapshotAdmin
from wallets.admin.transaction import TransactionAdmin
from wallets.admin.wallet import WalletAdmin

__all__ = [
    "TransactionAdmin",
    "FiatTransactionAdmin",
    "HoldingAdmin",
    "HoldingSnapshotAdmin",
    "WalletAdmin",
]
