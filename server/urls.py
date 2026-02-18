"""
URL configuration for server project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic.base import RedirectView
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from apps.admin.urls import admin_api_urlpatterns, admin_llm_urlpatterns
from apps.admin.views import admin_messages_view
from apps.chat.views import RegenerationView, PublicSharedChatView, ContinueChatView

urlpatterns = [
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/swagger/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger",
    ),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    # Admin extensions  
    path("admin/llm/nav/", include(admin_llm_urlpatterns)),
    path("admin/llm/messages-interface/", admin_messages_view, name="admin-messages-interface"),
    # Admin API endpoints  
    path("admin/llm/messages-interface/api/", include(admin_api_urlpatterns)),
    path("admin/", admin.site.urls),
    # JWT URLs (most specific first)
    path("api/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    # Djoser URLs - /api/auth/users/, /api/auth/users/me/, etc.
    path("api/auth/", include("djoser.urls")),
    path("api/auth/jwt/", include("djoser.urls.jwt")),
    # Social Django URLs (login/complete для Google, Twitter)
    path("api/auth/social/", include("social_django.urls")),
    # Custom auth endpoints (Apple OAuth2, Google One Tap, custom callbacks)
    path("api/auth/custom/", include("apps.users.urls")),
    path("api/payments/", include("apps.payments.urls")),
    path("api/", include("apps.usageLimits.urls")),
    # Regeneration endpoint
    path("api/regeneration/", RegenerationView.as_view(), name="regeneration"),
    # Chat endpoints (swagger.yaml + old server routes)
    path("api/chat/", include("apps.chat.urls")),
    # Public shared chat views (no auth required for GET)
    path("api/share/<str:token>/continue/", ContinueChatView.as_view(), name="continue-shared-chat"),
    path("api/share/<str:token>/", PublicSharedChatView.as_view(), name="public-shared-chat"),
    # Favicon redirect
    path("favicon.ico", RedirectView.as_view(url=settings.STATIC_URL + "favicon.ico")),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
