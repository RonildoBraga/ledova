from django.contrib import admin

from shared.models.country import Country


@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "dial_code", "is_available", "created_at")
    search_fields = ("name", "code")
    list_filter = ("is_available",)
