from django.urls import path

from . import views

urlpatterns = [
    path(
        "social/<str:provider>/",
        views.SocialAuthCallbackView.as_view(),
        name="social-auth",
    ),
]
