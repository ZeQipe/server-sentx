from rest_framework import serializers

from apps.ChatSessions.models import ChatSession
from apps.messages.models import Message
from apps.attachedFiles.models import AttachedFile
from apps.feedbacks.models import Feedback
from service.obfuscation import ObfuscatedIDField


class AttachedFileSerializer(serializers.ModelSerializer):
    id = ObfuscatedIDField(read_only=True)

    class Meta:
        model = AttachedFile
        fields = ["id", "file", "filename", "content_type", "created_at"]
        read_only_fields = ["id", "created_at"]


class MessageSerializer(serializers.ModelSerializer):
    id = ObfuscatedIDField(read_only=True)
    parentId = serializers.SerializerMethodField()
    currentVersion = serializers.IntegerField(source="current_version", read_only=True)
    totalVersions = serializers.IntegerField(source="total_versions", read_only=True)

    class Meta:
        model = Message
        fields = [
            "id", "uid", "role", "content", "version", "created_at",
            "parentId", "currentVersion", "totalVersions",
        ]
        read_only_fields = ["id", "uid", "created_at"]

    def get_parentId(self, obj):
        return obj.parent.uid if obj.parent_id else None


class FeedbackSerializer(serializers.ModelSerializer):
    id = ObfuscatedIDField(read_only=True)

    class Meta:
        model = Feedback
        fields = ["id", "is_liked", "comment", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class ChatSessionSerializer(serializers.ModelSerializer):
    id = ObfuscatedIDField(read_only=True)
    messages = serializers.SerializerMethodField()

    class Meta:
        model = ChatSession
        fields = ["id", "title", "created_at", "updated_at", "messages"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_title(self, value):
        if len(value) > 255:
            return value[:252] + "..."
        return value

    def get_messages(self, instance):
        from apps.chat.services import ChatService
        branch = ChatService.get_active_branch(instance)
        return MessageSerializer(branch, many=True).data

    def to_representation(self, instance):
        data = super().to_representation(instance)
        title = data.get("title", "")
        if len(title) > 80:
            data["title"] = title[:77] + "..."
        return data

