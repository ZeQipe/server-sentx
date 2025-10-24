from rest_framework import serializers
from service.obfuscation import ObfuscatedIDField


class SendMessageRequestSerializer(serializers.Serializer):
    """Serializer for sending messages (POST /chat/messages)"""

    content = serializers.CharField(required=True, allow_blank=False)
    chatId = ObfuscatedIDField(required=False, allow_null=True)

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


class ChatMessageSerializer(serializers.Serializer):
    """Serializer for chat messages"""

    messageId = serializers.CharField()
    chatId = serializers.CharField()
    role = serializers.ChoiceField(choices=["user", "assistant"])
    content = serializers.CharField()
    createdAt = serializers.DateTimeField()


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

