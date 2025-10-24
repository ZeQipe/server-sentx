from rest_framework import serializers

from .models import AnonymousUsageLimit


class AnonymousUsageLimitSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnonymousUsageLimit
        fields = [
            "requests_made_today",
            "last_reset_date",
        ]
        read_only_fields = fields
