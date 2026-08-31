from django.db.models import QuerySet


class BlockchainTransactionQuerySet(QuerySet):
    def pending(self):
        from blockchain.models import TransactionStatus

        return self.filter(status__in=[TransactionStatus.PENDING, TransactionStatus.SUBMITTED])

    def confirmed(self):
        from blockchain.models import TransactionStatus

        return self.filter(status=TransactionStatus.CONFIRMED)

    def failed(self):
        from blockchain.models import TransactionStatus

        return self.filter(status__in=[TransactionStatus.FAILED, TransactionStatus.REVERTED])

    def with_tx_hash(self):
        return self.filter(tx_hash__isnull=False)

    def stale(self, cutoff_datetime):
        return self.pending().filter(created_at__lt=cutoff_datetime)

    def with_optimized_data(self):
        return self.select_related("deployed_contract")
