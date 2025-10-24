from django.urls import path

from . import views

# Admin URL patterns (for /admin/llm/nav/)
admin_llm_urlpatterns = [
    path("", views.admin_index_redirect, name="llm-admin-root"),
]

# Admin API URLs - separate pattern list for admin endpoints
admin_api_urlpatterns = [
    path("filters/", views.AdminFiltersView.as_view(), name="admin-filters"),
    path("chats/", views.AdminChatsView.as_view(), name="admin-chats"),
    path("chats/messages/", views.AdminChatMessagesView.as_view(), name="admin-chat-messages"),
    path("breadcrumbs/", views.AdminBreadcrumbsView.as_view(), name="admin-breadcrumbs"),
    path("date-filters/", views.AdminDateFiltersView.as_view(), name="admin-date-filters"),
]
