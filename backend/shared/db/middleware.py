from .aliases import clear_alias, select_operator
from .principal import reset_principal

OPERATOR_MARKER = "runs_on_the_operator_connection"


class RunsOnTheOperatorConnection:
    runs_on_the_operator_connection = True


def view_runs_on_the_operator_connection(view, resolver_match) -> bool:
    if getattr(resolver_match, "app_name", "") == "admin":
        return True
    target = getattr(view, "cls", None) or getattr(view, "view_class", None) or view
    return bool(getattr(target, OPERATOR_MARKER, False))


class DatabaseIdentityMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            return self.get_response(request)
        finally:
            reset_principal()
            clear_alias()

    def process_view(self, request, view_func, view_args, view_kwargs):
        if view_runs_on_the_operator_connection(view_func, request.resolver_match):
            select_operator()
        return None
