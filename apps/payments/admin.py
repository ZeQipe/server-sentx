from django.contrib import admin

from .models import BillingPlan, Subscription


@admin.register(BillingPlan)
class BillingPlanAdmin(admin.ModelAdmin):
    list_display = ("name", "price", "interval", "created_at")
    search_fields = ("name",)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "plan",
        "start_date",
        "end_date",
        "is_active",
        "stripe_subscription_id",
    )
    list_filter = ("is_active", "plan")
    search_fields = ("user__email", "stripe_subscription_id")
