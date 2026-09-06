from users.models import DeviceToken


def register_device_token(user, push_token, device_type):
    return DeviceToken.objects.update_or_create(
        push_token=push_token,
        defaults={"user": user, "device_type": device_type, "is_active": True},
    )


def unregister_device_token(user, push_token):
    deleted, _ = DeviceToken.objects.visible_to_user(user).filter(push_token=push_token).delete()
    return deleted
