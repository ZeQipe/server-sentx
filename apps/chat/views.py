import json
import uuid
from datetime import datetime
from django.conf import settings

from django.http import StreamingHttpResponse
from rest_framework import status, views
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.ChatSessions.models import ChatSession
from apps.messages.models import Message
from service.obfuscation import Abfuscator
from .serializers import (
    ChatHistoryResponseSerializer,
    ChatMessageSerializer,
    SendMessageRequestSerializer,
    SendMessageResponseSerializer,
)
from .services import ChatService


class ChatMessagesView(views.APIView):
    """
    POST /chat/messages
    Send a message to the chat
    """

    permission_classes = [AllowAny]

    def get_client_ip(self, request):
        """Get client IP address"""
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0]
        else:
            ip = request.META.get("REMOTE_ADDR")
        return ip

    def post(self, request):
        """
        Send a message to the chat

        Request body:
            - content (required): Message content
            - chatId (optional): Chat ID (null for new chat or anonymous)
            - sessionId (optional): SSE session ID для отправки ответа через постоянное соединение

        Returns:
            - messageId: Created user message ID
            - chatId: Chat ID (permanent or temporary)
            - isTemporary: Whether chatId is temporary
        """
        serializer = SendMessageRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        content = serializer.validated_data["content"]
        chat_id = serializer.validated_data.get("chatId")
        session_id = request.data.get("sessionId")  # SSE session ID
        user = request.user if request.user.is_authenticated else None
        ip_address = self.get_client_ip(request)

        # Check usage limits before creating message
        can_proceed, error_msg = ChatService.check_usage_limits(user, ip_address)
        if not can_proceed:
            # Если есть SSE сессия, отправляем ошибку туда
            if session_id and hasattr(ChatService, '_sse_queues') and session_id in ChatService._sse_queues:
                ChatService._sse_queues[session_id]['queue'].put({
                    "error": error_msg or "Request limit exceeded",
                    "messageId": str(uuid.uuid4()),
                    "chatId": chat_id or ""
                })
            return Response(
                {"error": error_msg or "Request limit exceeded"},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        # Determine if this is a temporary session
        is_temporary = not user
        
        if not user:
            # Неавторизованный пользователь - всегда временный чат
            if not chat_id:
                chat_id = f"temp_{uuid.uuid4()}"
            temp_session = ChatService.get_or_create_temporary_session(chat_id)
            user_message_id = str(uuid.uuid4())
            ChatService.add_temporary_message(temp_session, "user", content, user_message_id)
            public_chat_id = chat_id
            is_temp = True
            db_chat_id = chat_id
        else:
            # Авторизованный пользователь
            if chat_id:
                # Продолжаем существующий чат
                try:
                    # chat_id уже деобфусцирован через сериализатор
                    chat_session = ChatSession.objects.get(id=chat_id, user=user)
                except ChatSession.DoesNotExist:
                    return Response(
                        {"error": "Chat session not found"},
                        status=status.HTTP_404_NOT_FOUND,
                    )
            else:
                # Создаем новый постоянный чат
                chat_session = ChatService.create_chat_session(user)
            
            db_chat_id = chat_session.id
            # Обфусцируем ID для ответа
            public_chat_id = Abfuscator.encode(
                salt=settings.ABFUSCATOR_ID_KEY, value=chat_session.id, min_length=17
            )
            
            # Save user message
            user_message = ChatService.add_message(chat_session, "user", content)
            user_message_id = user_message.uid
            is_temp = False

        # Если есть активное SSE соединение, отправляем ответ через него
        if session_id and hasattr(ChatService, '_sse_queues') and session_id in ChatService._sse_queues:
            sse_info = ChatService._sse_queues[session_id]
            message_queue = sse_info['queue']
            
            # Отправляем сообщение пользователя в SSE
            message_queue.put({
                "messageId": user_message_id,
                "chatId": public_chat_id,
                "role": "user",
                "content": content
            })
            
            # Запускаем генерацию ответа в отдельном потоке
            import threading
            
            def generate_response():
                stream = ChatService.process_chat_stream(
                    user, db_chat_id, content, ip_address, is_temporary
                )
                for chunk in stream:
                    # Подменяем chatId на публичный для постоянных чатов
                    if not is_temporary and isinstance(chunk, dict) and "chatId" in chunk:
                        chunk["chatId"] = public_chat_id
                    message_queue.put(chunk)
            
            thread = threading.Thread(target=generate_response)
            thread.daemon = True
            thread.start()

        # Return response
        response_data = {
            "messageId": user_message_id,
            "chatId": public_chat_id,
            "isTemporary": is_temp,
        }

        return Response(response_data, status=status.HTTP_200_OK)


class ChatStreamView(views.APIView):
    """
    GET /chat/stream
    Постоянное SSE соединение для получения ответов ассистента
    """

    permission_classes = [AllowAny]

    def get_client_ip(self, request):
        """Get client IP address"""
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0]
        else:
            ip = request.META.get("REMOTE_ADDR")
        return ip

    def get(self, request):
        """
        Постоянное SSE соединение для стриминга сообщений
        Соединение остается открытым для всех последующих ответов

        Query params:
            - chatId (optional): Initial chat ID

        Returns:
            Постоянный SSE stream
        """
        initial_chat_id = request.query_params.get("chatId")
        user = request.user if request.user.is_authenticated else None
        ip_address = self.get_client_ip(request)
        
        def event_stream():
            """
            Постоянный генератор SSE событий
            Держит соединение открытым и ждет новых сообщений
            """
            import queue
            import threading
            import time
            
            # Создаем очередь для этого SSE соединения
            message_queue = queue.Queue()
            session_id = str(uuid.uuid4())
            
            # Сохраняем очередь глобально для доступа из ChatMessagesView
            if not hasattr(ChatService, '_sse_queues'):
                ChatService._sse_queues = {}
            ChatService._sse_queues[session_id] = {
                'queue': message_queue,
                'user': user,
                'ip': ip_address,
                'chat_id': initial_chat_id
            }
            
            try:
                # Отправляем начальное сообщение с sessionId
                yield f"data: {json.dumps({'type': 'connected', 'sessionId': session_id})}\n\n"
                
                # Основной цикл - держим соединение открытым
                while True:
                    try:
                        # Ждем сообщение из очереди с таймаутом для heartbeat
                        message = message_queue.get(timeout=30)
                        
                        if message == "CLOSE":
                            break
                        
                        # Отправляем сообщение клиенту
                        yield f"data: {json.dumps(message, ensure_ascii=False)}\n\n"
                        
                    except queue.Empty:
                        # Отправляем heartbeat для поддержания соединения
                        yield f": heartbeat\n\n"
                        
            except GeneratorExit:
                # Соединение закрыто клиентом
                pass
            finally:
                # Очищаем очередь при закрытии соединения
                if session_id in ChatService._sse_queues:
                    del ChatService._sse_queues[session_id]

        response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        response["Connection"] = "keep-alive"
        return response


class ChatHistoryView(views.APIView):
    """
    GET /chat/history
    Get chat message history
    """

    permission_classes = [AllowAny]

    def get(self, request):
        """
        Get chat history (last 100 messages)

        Query params:
            - chatId (required): Chat ID

        Returns:
            - chatId: Chat ID
            - messages: List of messages
        """
        chat_id = request.query_params.get("chatId")
        if not chat_id:
            return Response(
                {"error": "chatId is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        user = request.user if request.user.is_authenticated else None
        is_temporary = chat_id.startswith("temp_")
        public_chat_id = chat_id

        if is_temporary:
            # Get temporary chat history
            messages = ChatService.get_temporary_chat_history(chat_id)
            response_data = {"chatId": public_chat_id, "messages": messages}
        else:
            # Get permanent chat history
            try:
                if user:
                    db_chat_id = Abfuscator.decode(salt=settings.ABFUSCATOR_ID_KEY, value=chat_id)
                    chat_session = ChatSession.objects.get(id=db_chat_id, user=user)
                else:
                    return Response(
                        {"error": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED
                    )
            except ChatSession.DoesNotExist:
                return Response(
                    {"error": "Chat session not found"}, status=status.HTTP_404_NOT_FOUND
                )

            history = ChatService.get_chat_history(chat_session)
            messages = [
                {
                    "messageId": msg.uid,
                    "chatId": public_chat_id,
                    "role": msg.role,
                    "content": msg.content,
                    "createdAt": msg.created_at.isoformat(),
                }
                for msg in history
            ]
            response_data = {"chatId": public_chat_id, "messages": messages}

        return Response(response_data, status=status.HTTP_200_OK)


class ChatRegenerateView(views.APIView):
    """
    POST /chat/messages/regenerate
    Пересоздать ответ ассистента, начиная с выбранного сообщения, по логике старого сервера.
    Ожидает поля: chat_session_id (обфусцированный), message_id (uid сообщения ассистента)
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        chat_session_id = request.data.get("chat_session_id")
        message_id = request.data.get("message_id")

        if not chat_session_id:
            return Response({"error": "chat_session_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not message_id:
            return Response({"error": "message_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Deobfuscate chat_session_id
        try:
            if isinstance(chat_session_id, str) and not chat_session_id.isdigit():
                deobfuscated_id = Abfuscator.decode(salt=settings.ABFUSCATOR_ID_KEY, value=chat_session_id)
            else:
                deobfuscated_id = int(chat_session_id)
        except (ValueError, Exception):
            return Response({"error": "Invalid chat_session_id format"}, status=status.HTTP_400_BAD_REQUEST)

        # Verify chat session ownership
        try:
            chat_session = ChatSession.objects.get(id=deobfuscated_id, user=request.user)
        except ChatSession.DoesNotExist:
            return Response({"error": "Chat session not found"}, status=status.HTTP_404_NOT_FOUND)

        # Find target message
        try:
            target_message = Message.objects.get(uid=message_id, chat_session=chat_session)
        except Message.DoesNotExist:
            return Response({"error": "Message not found in this chat session"}, status=status.HTTP_404_NOT_FOUND)

        # Only assistant messages can be regenerated
        if target_message.role == "user":
            return Response({"error": "Can only regenerate from assistant messages"}, status=status.HTTP_400_BAD_REQUEST)

        # Build history up to target message (exclusive)
        history = Message.objects.filter(
            chat_session=chat_session,
            created_at__lt=target_message.created_at,
        ).order_by("created_at")

        # Delete all messages after target message and the target itself
        Message.objects.filter(
            chat_session=chat_session,
            created_at__gt=target_message.created_at,
        ).order_by("created_at").all().delete()
        target_message.delete()

        # Prepare messages for LLM
        api_messages = [{"role": msg.role, "content": msg.content} for msg in history]

        # SSE stream
        def event_stream():
            client = ChatService.get_llm_client()
            assistant_message_id = str(uuid.uuid4())
            public_chat_id = Abfuscator.encode(salt=settings.ABFUSCATOR_ID_KEY, value=chat_session.id, min_length=17)
            full_content = ""

            try:
                stream = client.chat(api_messages, stream=True)
                for chunk in stream:
                    # Check for errors
                    if isinstance(chunk, dict) and "error" in chunk:
                        yield f"data: {json.dumps({'error': chunk['error'], 'messageId': assistant_message_id, 'chatId': public_chat_id})}\n\n"
                        return

                    # Extract content from chunk
                    choices = chunk.get("choices", []) if isinstance(chunk, dict) else []
                    if not choices:
                        continue
                    delta = choices[0].get("delta", {})
                    content_part = delta.get("content")
                    if content_part:
                        full_content += content_part
                        data = {
                            "messageId": assistant_message_id,
                            "chatId": public_chat_id,
                            "role": "assistant",
                            "content": full_content,
                            "resolveMessage": False,
                        }
                        yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

                # Save assistant message
                ChatService.add_message(chat_session, "assistant", full_content, uuid.UUID(assistant_message_id))

                # Final message with resolveMessage flag (no limit increment here to match old logic)
                final = {
                    "messageId": assistant_message_id,
                    "chatId": public_chat_id,
                    "role": "assistant",
                    "content": full_content,
                    "resolveMessage": ChatService.should_show_resolve_message(request.user),
                }
                yield f"data: {json.dumps(final, ensure_ascii=False)}\n\n"

            except Exception as e:
                import traceback
                traceback.print_exc()
                yield f"data: {json.dumps({'error': f'Error processing request: {str(e)}', 'messageId': assistant_message_id, 'chatId': public_chat_id})}\n\n"
            
            # Не отправляем [DONE] - клиент понимает по messageId когда стрим завершен

        response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response
