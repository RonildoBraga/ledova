from django.urls import path

from operators.views import OperatorView

app_name = "operators"

urlpatterns = [
    path("", OperatorView.as_view(), name="operator"),
]
