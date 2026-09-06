from rest_framework.routers import DefaultRouter

from offerings.views import SubscriptionViewSet

app_name = "subscriptions"

router = DefaultRouter()
router.register(r"", SubscriptionViewSet, basename="subscriptions")

urlpatterns = router.urls
