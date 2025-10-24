from rest_framework import serializers

from .models import Feedback


class FeedbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = Feedback
        fields = ["id", "is_liked", "comment", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]
