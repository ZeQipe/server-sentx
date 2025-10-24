from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ChatHistoryView, ChatMessagesView, ChatStreamView, ChatRegenerateView
from .viewsets import ChatSessionViewSet, MessageViewSet

# Create router for viewsets
router = DefaultRouter()
router.register(r"sessions", ChatSessionViewSet, basename="chat-session")
router.register(r"messages-list", MessageViewSet, basename="message")

urlpatterns = [
    # Swagger.yaml endpoints (priority)
    path("messages", ChatMessagesView.as_view(), name="chat-messages"),
    path("messages/regenerate", ChatRegenerateView.as_view(), name="chat-regenerate"),
    path("stream", ChatStreamView.as_view(), name="chat-stream"),
    path("history", ChatHistoryView.as_view(), name="chat-history"),
    # ViewSet endpoints (from old server)
    path("", include(router.urls)),
]

