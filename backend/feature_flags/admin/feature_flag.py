from django.contrib import admin

from feature_flags.models.feature_flag import FeatureFlag


@admin.register(FeatureFlag)
class FeatureFlagAdmin(admin.ModelAdmin):
    list_display = ["name", "enabled", "platform", "min_app_version", "description", "created_at", "updated_at"]
    list_editable = ("enabled",)
    list_filter = ["enabled", "platform"]
    search_fields = ["name", "description"]
    readonly_fields = ["uuid", "created_at", "updated_at"]
