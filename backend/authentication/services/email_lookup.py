from django.contrib.auth import get_user_model

from authentication.managers.user import EmailLookupState

User = get_user_model()


def find_unique_user(email):
    lookup = User.objects.resolve_email(email)

    return lookup.user if lookup.state is EmailLookupState.UNIQUE else None
