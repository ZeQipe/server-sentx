from rest_framework import serializers

from .models import UsageLimit


class UsageLimitSerializer(serializers.ModelSerializer):
    class Meta:
        model = UsageLimit
        fields = [
            "free_requests_limit",
            "paid_requests_limit",
            "requests_made_today",
            "last_reset_date",
        ]
        read_only_fields = fields
