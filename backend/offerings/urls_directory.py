from rest_framework.routers import DefaultRouter

from offerings.views import DirectoryTokenViewSet

app_name = "directory"

router = DefaultRouter()
router.register(r"tokens", DirectoryTokenViewSet, basename="tokens")

urlpatterns = router.urls
