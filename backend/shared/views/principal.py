from asgiref.sync import sync_to_async

from shared.db import select_operator, set_principal

PRINCIPAL_MARKER = "sets_the_principal"


class SetsThePrincipalOnTheConnection:
    sets_the_principal = True
    operator_actions: frozenset = frozenset()

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if getattr(self, "action", None) in self.operator_actions:
            select_operator()
            return
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            set_principal(user.pk)


def sets_the_principal(view):
    view.sets_the_principal = True
    return view


async def set_principal_for_async_view(user) -> None:
    if user is not None and user.is_authenticated:
        await sync_to_async(set_principal, thread_sensitive=True)(user.pk)
