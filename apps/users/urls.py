from django.urls import path

from . import views

urlpatterns = [
    # Apple OAuth2 endpoints - ПЕРВЫМИ (более специфичные)
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
    # Google One Tap
    path(
        "google-one-tap/",
        views.GoogleOneTapView.as_view(),
        name="google-one-tap",
    ),
    # Generic social auth callback - ПОСЛЕДНИМ (generic паттерн)
    path(
        "<str:provider>/callback/",
        views.SocialAuthCallbackView.as_view(),
        name="social-auth",
    ),
]
