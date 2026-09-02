from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import BaseUserCreationForm
from django.utils.translation import gettext_lazy as _

from authentication.managers.user import V2EmailLookupState
from authentication.models.user import CustomUser
from authentication.security.v2_email import V2EmailError, normalize_v2_email


class V2UserCreationForm(BaseUserCreationForm):
    email = forms.CharField(max_length=254, strip=False, widget=forms.EmailInput)

    class Meta:
        model = CustomUser
        fields = ("email",)

    def clean_email(self):
        try:
            destination_key = normalize_v2_email(self.cleaned_data["email"])
        except V2EmailError:
            raise forms.ValidationError("Enter a valid email address.", code="invalid") from None
        lookup = CustomUser.objects.resolve_v2_email(destination_key)
        if lookup.state is not V2EmailLookupState.ABSENT:
            raise forms.ValidationError("Email is unavailable.", code="unavailable")
        return destination_key


class CustomUserAdmin(UserAdmin):
    model = CustomUser
    add_form = V2UserCreationForm
    list_display = (
        "email",
        "is_active",
        "is_staff",
        "is_email_verified",
        "is_phone_verified",
        "email_verification_token",
    )
    list_filter = ("is_active", "is_staff", "is_email_verified", "is_phone_verified")
    search_fields = ("email",)
    ordering = ("email",)

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Personal info"), {"fields": ("is_email_verified", "is_phone_verified")}),
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

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        return (*fields, "email") if obj is not None else fields


admin.site.register(CustomUser, CustomUserAdmin)
