from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()

INTERVAL_CHOICES = [
    ("month", "Monthly"),
    ("year", "Yearly"),
]


class BillingPlan(models.Model):
    name = models.CharField(max_length=255)
    price = models.IntegerField()
    description = models.TextField()
    stripe_price_id = models.CharField(max_length=255, null=True, blank=True)
    stripe_product_id = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    interval = models.CharField(
        max_length=255, choices=INTERVAL_CHOICES, default="month"
    )

    def __str__(self):
        return self.name


class Subscription(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    plan = models.ForeignKey(BillingPlan, on_delete=models.CASCADE)
    stripe_subscription_id = models.CharField(max_length=255, null=True, blank=True)
    start_date = models.DateTimeField(auto_now_add=True)
    end_date = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return (
            f"{self.user.email} - {self.plan.name} {self.start_date} - {self.end_date}"
        )
