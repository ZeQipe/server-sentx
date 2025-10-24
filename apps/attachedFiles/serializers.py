from rest_framework import serializers

from .models import AttachedFile


class AttachedFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttachedFile
        fields = ["id", "file", "filename", "content_type", "created_at"]
        read_only_fields = ["id", "created_at"]
