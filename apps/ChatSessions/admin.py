from django.contrib import admin

from .models import ChatSession


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "title", "created_at", "updated_at")
    list_filter = ("created_at", "updated_at")
    search_fields = ("title",)
    date_hierarchy = "created_at"
    
    class Media:
        js = ('admin/js/custom_admin.js',)
