from django.contrib import admin

from .models import AttachedFile


@admin.register(AttachedFile)
class AttachedFileAdmin(admin.ModelAdmin):
    list_display = ("id", "message", "filename", "content_type", "created_at")
    list_filter = ("content_type", "created_at")
    search_fields = ("filename", "message__content")
    date_hierarchy = "created_at"
    
    class Media:
        js = ('admin/js/custom_admin.js',)
