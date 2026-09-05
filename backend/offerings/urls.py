from rest_framework.routers import DefaultRouter

from offerings.views import OfferingViewSet

app_name = "offerings"

router = DefaultRouter()
router.register(r"", OfferingViewSet, basename="offerings")

urlpatterns = router.urls
