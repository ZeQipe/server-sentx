from rest_framework import serializers
from service.obfuscation import ObfuscatedIDField


class SendMessageRequestSerializer(serializers.Serializer):
    """Serializer for sending messages (POST /chat/messages)"""

    content = serializers.CharField(required=True, allow_blank=False)
    chatId = ObfuscatedIDField(required=False, allow_null=True)
    editMessageId = serializers.CharField(required=False, allow_null=True, default=None)

    def validate_content(self, value):
        """Validate that content is not empty"""
        if not value or not value.strip():
            raise serializers.ValidationError("Message content cannot be blank")
        return value


class SendMessageResponseSerializer(serializers.Serializer):
    """Serializer for send message response"""

    messageId = serializers.CharField()
    chatId = serializers.CharField()
    isTemporary = serializers.BooleanField()
    parentId = serializers.CharField(allow_null=True)
    currentVersion = serializers.IntegerField()
    totalVersions = serializers.IntegerField()


class ChatMessageSerializer(serializers.Serializer):
    """Serializer for chat messages"""

    messageId = serializers.CharField()
    chatId = serializers.CharField()
    role = serializers.ChoiceField(choices=["user", "assistant"])
    content = serializers.CharField()
    v = serializers.CharField()
    createdAt = serializers.DateTimeField()
    parentId = serializers.CharField(allow_null=True)
    currentVersion = serializers.IntegerField()
    totalVersions = serializers.IntegerField()


class ChatHistoryResponseSerializer(serializers.Serializer):
    """Serializer for chat history response"""

    chatId = serializers.CharField()
    messages = ChatMessageSerializer(many=True)


class SSEMessageSerializer(serializers.Serializer):
    """Serializer for SSE stream messages"""

    messageId = serializers.CharField()
    chatId = serializers.CharField()
    role = serializers.ChoiceField(choices=["user", "assistant"])
    content = serializers.CharField()
    resolveMessage = serializers.BooleanField()
    parentId = serializers.CharField(allow_null=True)
    currentVersion = serializers.IntegerField()
    totalVersions = serializers.IntegerField()


class SwitchBranchRequestSerializer(serializers.Serializer):
    """Serializer for switch-branch request (POST /chat/switch-branch/)"""

    chatId = ObfuscatedIDField(required=True)
    parentId = serializers.CharField(required=False, allow_null=True, default=None)
    newVersion = serializers.IntegerField(required=True, min_value=1)


class RegenerationRequestSerializer(serializers.Serializer):
    """Serializer for regeneration request (POST /api/regeneration/)"""

    messageId = serializers.CharField(required=True)
    sessionId = serializers.CharField(required=True)
    parentId = serializers.CharField(required=True)
    chatId = ObfuscatedIDField(required=True)


class ShareChatRequestSerializer(serializers.Serializer):
    """POST /api/chat/share/ — создать ссылку на снимок чата"""

    chatId = ObfuscatedIDField(required=True)


class RevokShareRequestSerializer(serializers.Serializer):
    """DELETE /api/chat/share/ — отозвать ссылку"""

    chatId = ObfuscatedIDField(required=True)
