from django.db.models import QuerySet


class ContractDeploymentQuerySet(QuerySet):
    def active(self):
        return self.filter(is_active=True)

    def verified(self):
        return self.filter(is_verified=True)

    def with_optimized_data(self):
        return self.select_related("deployment_tx")
