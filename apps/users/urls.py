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
    # Apple OAuth2 endpoints
    path(
        "apple/login/",
        views.AppleLoginView.as_view(),
        name="apple-login",
    ),
    path(
        "apple/callback/",
        views.AppleCallbackView.as_view(),
        name="apple-callback",
    ),
    path(
        "apple/user/",
        views.AppleUserView.as_view(),
        name="apple-user",
    ),
]
