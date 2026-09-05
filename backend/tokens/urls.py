from rest_framework.routers import DefaultRouter

from tokens import views

app_name = "tokens"

router = DefaultRouter()
router.register(r"capital-increases", views.CapitalIncreaseViewSet, basename="capital-increases")
router.register(r"", views.ShareTokenViewSet, basename="tokens")

urlpatterns = router.urls
