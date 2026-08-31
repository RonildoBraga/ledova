from rest_framework.routers import DefaultRouter

from tokens import views

app_name = "tokens"

router = DefaultRouter()
router.register(r"capital-increases", views.CapitalIncreaseViewSet, basename="capital-increases")
router.register(r"orders", views.TransferOrderViewSet, basename="orders")
router.register(r"yield-tokens", views.YieldTokenViewSet, basename="yield-tokens")
router.register(r"", views.ShareTokenViewSet, basename="tokens")

urlpatterns = router.urls
