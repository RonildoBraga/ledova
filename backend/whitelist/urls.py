from django.urls import include, path
from rest_framework.routers import DefaultRouter

from whitelist import views

app_name = "whitelist"

router = DefaultRouter()
router.register(r"", views.WhitelistEntryViewSet, basename="whitelist")

urlpatterns = [
    path("", include(router.urls)),
]
