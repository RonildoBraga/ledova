from django.core.exceptions import ImproperlyConfigured

NO_MODEL = (
    "{view} sets manage_actions or narrow() but names no scoped_model, so the base cannot tell "
    "which manager to scope. Set scoped_model, or drop the hook."
)
BOTH = (
    "{view} names a scoped_model and also defines {hook}. The base owns the scoping call; put the "
    "product filtering in narrow(), which receives the already-scoped queryset."
)
NO_PREDICATE = (
    "{view} scopes {model}, whose manager has no {predicate}. A view cannot be scoped to a principal "
    "through a manager that offers no way to do it."
)
WIDER_THAN_ADMIN = (
    "{view} routes {actions} to the operator connection without naming them administrative. An "
    "unscoped read is keyed to administrative_actions because that is the set get_permissions turns "
    "into IsAdminUser; operator_actions only chooses a connection, and the coverage gate lets it be "
    "the wider of the two."
)
NO_MANAGE_PREDICATE = (
    "{view} lists manage_actions for {model}, whose manager has no manageable_by_user. Writes would "
    "silently take the read scope, which is wider."
)


class ScopesToThePrincipal:

    scoped_model = None
    manage_actions: frozenset = frozenset()

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        model = cls.scoped_model
        if model is None:
            if cls.__dict__.get("manage_actions") or "narrow" in cls.__dict__:
                raise ImproperlyConfigured(NO_MODEL.format(view=cls.__name__))
            return
        for hook in ("get_queryset", "get_object"):
            if hook in cls.__dict__:
                raise ImproperlyConfigured(BOTH.format(view=cls.__name__, hook=hook))
        manager = model._default_manager
        if not hasattr(manager, "visible_to_user"):
            raise ImproperlyConfigured(
                NO_PREDICATE.format(view=cls.__name__, model=model.__name__, predicate="visible_to_user")
            )
        if cls.manage_actions and not hasattr(manager, "manageable_by_user"):
            raise ImproperlyConfigured(NO_MANAGE_PREDICATE.format(view=cls.__name__, model=model.__name__))
        wider = frozenset(getattr(cls, "operator_actions", ())) - frozenset(getattr(cls, "administrative_actions", ()))
        if wider:
            raise ImproperlyConfigured(WIDER_THAN_ADMIN.format(view=cls.__name__, actions=sorted(wider)))

    def get_queryset(self):
        manager = self.scoped_model._default_manager
        action = getattr(self, "action", None)
        if action in frozenset(getattr(self, "administrative_actions", ())):
            return self.narrow(manager.all())
        user = self.request.user
        if action in self.manage_actions:
            return self.narrow(manager.manageable_by_user(user))
        return self.narrow(manager.visible_to_user(user))

    def narrow(self, queryset):
        return queryset
