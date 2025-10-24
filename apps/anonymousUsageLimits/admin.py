from django.contrib import admin

from .models import AnonymousUsageLimit


@admin.register(AnonymousUsageLimit)
class AnonymousUsageLimitAdmin(admin.ModelAdmin):
    class Media:
        js = ('admin/js/custom_admin.js',)
