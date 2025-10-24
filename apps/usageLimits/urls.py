from django.urls import path

from .views import UsageLimitView

urlpatterns = [
    path("usage-limits/", UsageLimitView.as_view(), name="usage-limits"),
]
