from rest_framework import serializers

from .models import BillingPlan, Subscription


class BillingPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = BillingPlan
        fields = ["id", "name", "price", "description", "interval"]


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = BillingPlanSerializer()

    class Meta:
        model = Subscription
        fields = ["id", "plan", "start_date", "end_date", "is_active"]
