from django.urls import include, path
from rest_framework.routers import DefaultRouter

from companies import views

app_name = "companies"

router = DefaultRouter()
router.register(r"", views.CompanyViewSet, basename="companies")

document_router = DefaultRouter()
document_router.register(r"", views.DocumentViewSet, basename="documents")

urlpatterns = [
    path("", include(router.urls)),
    path("<uuid:company_uuid>/documents/", include(document_router.urls)),
    # TODO: Add company wallet endpoints after adapting to Ledova's Wallet model
]
