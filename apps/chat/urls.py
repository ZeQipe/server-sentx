from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ChatHistoryView, ChatMessagesView, ChatStreamView, ChatRegenerateView, ChatPongView
from .viewsets import ChatSessionViewSet, MessageViewSet
from .persistent_views import PersistentChatStreamView, PersistentChatMessagesView

# Create router for viewsets
router = DefaultRouter()
router.register(r"sessions", ChatSessionViewSet, basename="chat-session")
router.register(r"messages-list", MessageViewSet, basename="message")

urlpatterns = [
    # Swagger.yaml endpoints (priority)
    path("sessions/list/", ChatSessionViewSet.as_view({'get': 'with_last_message'}), name="chat-sessions-list"),
    path("messages/", ChatMessagesView.as_view(), name="chat-messages"),
    path("messages/regenerate/", ChatRegenerateView.as_view(), name="chat-regenerate"),
    path("stream/", ChatStreamView.as_view(), name="chat-stream"),
    path("pong/", ChatPongView.as_view(), name="chat-pong"),
    path("history/", ChatHistoryView.as_view(), name="chat-history"),
    
    # Persistent SSE connection endpoints
    path("persistent-stream", PersistentChatStreamView.as_view(), name="chat-persistent-stream"),
    path("persistent-messages", PersistentChatMessagesView.as_view(), name="chat-persistent-messages"),
    
    # ViewSet endpoints (from old server)
    path("", include(router.urls)),
]

