from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    BillingPlanViewSet,
    StripeWebhookView,
    SubscriptionViewSet,
)

router = DefaultRouter()
router.register(r"billing-plans", BillingPlanViewSet)
router.register(r"subscriptions", SubscriptionViewSet)


urlpatterns = [
    path("", include(router.urls)),
    path("webhooks/stripe/", StripeWebhookView.as_view(), name="stripe-webhook"),
]
