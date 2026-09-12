from django.db.models import QuerySet

from .aliases import OPERATOR_ALIAS, current_alias

ON_THE_OPERATOR_CONNECTION = (
    "{model}.for_the_current_principal() was evaluated on the operator connection, which has no "
    "principal and is not narrowed by the policy. A customer-facing view must run on the scoped "
    "connection; an operator caller wants the plain manager and its own explicit filter."
)


class CarriedByThePolicy(QuerySet):

    def for_the_current_principal(self):
        if current_alias() == OPERATOR_ALIAS:
            raise RuntimeError(ON_THE_OPERATOR_CONNECTION.format(model=self.model.__name__))
        return self
