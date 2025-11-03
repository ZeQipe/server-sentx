from django.conf import settings
from django.db.models import Max
from django.http import Http404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.ChatSessions.models import ChatSession
from apps.messages.models import Message
from apps.attachedFiles.service import AttachedFileService
from apps.feedbacks.service import FeedbackService
from service.obfuscation import ObfuscatedLookupMixin, Abfuscator
from .viewset_serializers import (
    AttachedFileSerializer,
    ChatSessionSerializer,
    FeedbackSerializer,
    MessageSerializer,
)


class ChatSessionViewSet(ObfuscatedLookupMixin, viewsets.ModelViewSet):
    """
    API endpoint for managing chat sessions
    CRUD for chat sessions: /chat/sessions/
    """

    serializer_class = ChatSessionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ChatSession.objects.none()
        return ChatSession.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        validated_data = serializer.validated_data
        title = validated_data.get("title", "")
        if len(title) > 255:
            validated_data["title"] = title[:252] + "..."
        serializer.save(user=self.request.user, **validated_data)

    @action(detail=False, methods=["get"])
    def with_last_message(self, request):
        """Get all chat sessions with their last message"""
        print(f"\n=== with_last_message request ===")
        print(f"User: {request.user.id}")

        # Get all chat sessions for the user
        chat_sessions = ChatSession.objects.filter(user=request.user)
        print(f"Chat sessions count: {chat_sessions.count()}")

        # For each chat session, prefetch the latest message
        chat_sessions = chat_sessions.annotate(
            last_message_time=Max("messages__created_at")
        ).order_by("-last_message_time")

        # Prepare the response data
        result = []
        salt = settings.ABFUSCATOR_ID_KEY
        for session in chat_sessions:
            obfuscated_id = Abfuscator.encode(salt=salt, value=session.id)
            
            # Логируем обфусцированный ID
            print(f"Session DB ID: {session.id} -> Obfuscated ID: {obfuscated_id}")

            result.append({
                "chatId": obfuscated_id,
                "title": session.title
            })

        print(f"Returning {len(result)} chat sessions with obfuscated IDs")
        return Response(result)


class MessageViewSet(ObfuscatedLookupMixin, viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for retrieving messages (read-only)
    GET /chat/messages/ - list messages
    GET /chat/messages/{uid}/ - get specific message
    POST /chat/messages/{uid}/attach_file/ - attach file
    POST /chat/messages/{uid}/feedback/ - add feedback
    """

    serializer_class = MessageSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "uid"

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Message.objects.none()
        return Message.objects.filter(chat_session__user=self.request.user)

    @action(detail=False, methods=["get"])
    def chat_history(self, request):
        """Get all messages for a specific chat session"""
        chat_session_id = request.query_params.get("chat_session_id")

        print(f"\n=== chat_history request ===")
        print(f"Obfuscated ID: {chat_session_id}")
        print(f"User: {request.user.id if request.user.is_authenticated else 'Anonymous'}")

        if not chat_session_id:
            return Response(
                {"error": "chat_session_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Deobfuscate chat_session_id
        salt = settings.ABFUSCATOR_ID_KEY
        print(f"Salt: {salt}")
        
        try:
            if isinstance(chat_session_id, str) and not chat_session_id.isdigit():
                print(f"Attempting to deobfuscate: {chat_session_id}")
                deobfuscated_id = Abfuscator.decode(salt=salt, value=chat_session_id)
                print(f"Deobfuscated ID: {deobfuscated_id}")
            else:
                deobfuscated_id = int(chat_session_id)
                print(f"Using numeric ID: {deobfuscated_id}")
        except (ValueError, Exception) as e:
            print(f"!!! Deobfuscation failed: {e}")
            return Response(
                {"error": "Invalid chat_session_id format"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Verify the chat session belongs to the user
            chat_session = ChatSession.objects.get(
                id=deobfuscated_id, user=request.user
            )
            print(f"Chat session found: {chat_session.id}")

            messages = Message.objects.filter(chat_session=chat_session)
            print(f"Messages count: {messages.count()}")
            serializer = self.get_serializer(messages, many=True)

            return Response(serializer.data)

        except ChatSession.DoesNotExist:
            print(f"!!! Chat session NOT FOUND - ID: {deobfuscated_id}, User: {request.user.id}")
            return Response(
                {"error": "Chat session not found"}, status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser, FormParser])
    def attach_file(self, request, uid=None):
        """Attach a file to a message"""
        try:
            message = self.get_object()

            if not request.FILES.get("file"):
                return Response(
                    {"error": "No file provided"}, status=status.HTTP_400_BAD_REQUEST
                )

            uploaded_file = request.FILES["file"]
            filename = request.data.get("filename", uploaded_file.name)
            content_type = uploaded_file.content_type

            attached_file = AttachedFileService.attach_file(
                message=message,
                file=uploaded_file,
                filename=filename,
                content_type=content_type,
            )

            serializer = AttachedFileSerializer(attached_file)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except Message.DoesNotExist:
            raise Http404

    @action(url_path="feedback", detail=True, methods=["post"])
    def feedback(self, request, uid=None):
        """Add feedback to an assistant message"""
        try:
            message = self.get_object()

            # Only assistant messages can receive feedback
            if message.role != "assistant":
                return Response(
                    {"error": "Only assistant messages can receive feedback"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            serializer = FeedbackSerializer(data=request.data)
            if serializer.is_valid():
                feedback = FeedbackService.add_feedback(
                    message=message,
                    is_liked=serializer.validated_data.get("is_liked"),
                    comment=serializer.validated_data.get("comment"),
                )
                response_serializer = FeedbackSerializer(feedback)
                return Response(response_serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except Message.DoesNotExist:
            raise Http404

