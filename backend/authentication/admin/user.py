from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import BaseUserCreationForm, UserChangeForm
from django.utils.translation import gettext_lazy as _

from authentication.email import EmailError, normalize_email
from authentication.managers.user import EmailLookupState
from authentication.models.user import CustomUser
from authentication.services.tokens import TokenService


def clean_destination_key(raw_email, owner_pk=None):
    """The stored address must be canonical and unique (model constraints); only `owner_pk` may
    already hold it, so a change form accepts its own address and a creation form none."""
    try:
        destination_key = normalize_email(raw_email)
    except EmailError:
        raise forms.ValidationError("Enter a valid email address.", code="invalid") from None
    lookup = CustomUser.objects.resolve_email(destination_key)
    holder_pk = lookup.user.pk if lookup.state is EmailLookupState.UNIQUE else None
    if lookup.state is not EmailLookupState.ABSENT and (owner_pk is None or holder_pk != owner_pk):
        raise forms.ValidationError("Email is unavailable.", code="unavailable")
    return destination_key


class CustomUserCreationForm(BaseUserCreationForm):
    email = forms.CharField(max_length=254, strip=False, widget=forms.EmailInput)

    class Meta:
        model = CustomUser
        fields = ("email",)

    def clean_email(self):
        return clean_destination_key(self.cleaned_data["email"])


class CustomUserChangeForm(UserChangeForm):
    email = forms.CharField(max_length=254, strip=False, widget=forms.EmailInput)

    class Meta(UserChangeForm.Meta):
        model = CustomUser

    def clean_email(self):
        return clean_destination_key(self.cleaned_data["email"], owner_pk=self.instance.pk)


class CustomUserAdmin(UserAdmin):
    model = CustomUser
    form = CustomUserChangeForm
    add_form = CustomUserCreationForm
    list_display = ("email", "is_active", "is_staff", "is_email_verified")
    list_filter = ("is_active", "is_staff", "is_email_verified")
    search_fields = ("email",)
    ordering = ("email",)

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Personal info"), {"fields": ("is_email_verified",)}),
        (_("Permissions"), {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2"),
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        """A changed address ends every session and must be proven again at the next sign-in:
        the old one may no longer belong to this person and the new one is unverified."""
        email_changed = change and form.initial.get("email") != obj.email
        if email_changed:
            obj.is_email_verified = False
        super().save_model(request, obj, form, change)
        if email_changed:
            TokenService.revoke_all(obj)


admin.site.register(CustomUser, CustomUserAdmin)
