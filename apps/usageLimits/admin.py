from django.contrib import admin

from .models import UsageLimit


@admin.register(UsageLimit)
class UsageLimitAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "free_requests_limit",
        "paid_requests_limit",
        "requests_made_today",
        "last_reset_date",
    )
    list_filter = ("last_reset_date",)
    
    class Media:
        js = ('admin/js/custom_admin.js',)
