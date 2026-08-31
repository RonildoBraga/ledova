from django.urls import include, path
from rest_framework.routers import DefaultRouter

from documents.views import DocumentViewSet

app_name = "documents"

router = DefaultRouter()
router.register(r"", DocumentViewSet, basename="documents")

urlpatterns = [
    path("", include(router.urls)),
]
