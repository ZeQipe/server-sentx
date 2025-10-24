from django.contrib import admin

from .models import Feedback


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ("id", "message", "is_liked", "created_at", "updated_at")
    list_filter = ("is_liked", "created_at")
    search_fields = ("message__content", "comment")
    date_hierarchy = "created_at"
    
    class Media:
        js = ('admin/js/custom_admin.js',)
