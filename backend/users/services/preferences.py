from django.db import transaction

from users.models import NotificationPreferences, UserPreferences, UserProfile


@transaction.atomic
def upsert_user_preferences(user, fields):
    return _upsert(UserPreferences, user, fields)


@transaction.atomic
def upsert_notification_preferences(user, fields):
    return _upsert(NotificationPreferences, user, fields)


def _profile_locked_against_a_concurrent_upsert(user):
    return UserProfile.objects.select_for_update().get(user=user)


def _upsert(model, user, fields):
    user_profile = _profile_locked_against_a_concurrent_upsert(user)
    existing = model.objects.filter(user_profile=user_profile).first()

    if existing is None:
        return model.objects.create(user_profile=user_profile, **fields)

    for name, value in fields.items():
        setattr(existing, name, value)
    existing.save(update_fields=[*fields, "updated_at"])
    return existing
