from django.contrib import admin

from apps.attachedFiles.models import AttachedFile
from .models import Message


class AttachedFileInline(admin.TabularInline):
    model = AttachedFile
    extra = 0


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("uid", "chat_session", "role", "short_content", "created_at")
    list_filter = ("role", "created_at")
    search_fields = ("content",)
    date_hierarchy = "created_at"
    inlines = [AttachedFileInline]

    def short_content(self, obj):
        return obj.content[:50] + ("..." if len(obj.content) > 50 else "")

    short_content.short_description = "Content"
    
    class Media:
        js = ('admin/js/custom_admin.js',)
