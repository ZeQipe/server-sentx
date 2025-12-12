from django.urls import path

from . import views

urlpatterns = [
    path(
        "<str:provider>/callback/",
        views.SocialAuthCallbackView.as_view(),
        name="social-auth",
    ),
    path(
        "google-one-tap/",
        views.GoogleOneTapView.as_view(),
        name="google-one-tap",
    ),
]
