import json
import uuid
from datetime import datetime
from django.conf import settings
from django.utils import timezone

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
            # Если есть SSE сессия, отправляем ошибку на ВСЕ соединения
            if session_id and hasattr(ChatService, '_sse_queues') and session_id in ChatService._sse_queues:
                error_data = {
                    "error": error_msg or "Request limit exceeded",
                    "messageId": str(uuid.uuid4()),
                    "chatId": chat_id or ""
                }
                for connection in ChatService._sse_queues[session_id]:
                    connection['queue'].put(error_data)
            return Response(
                {"error": error_msg or "Request limit exceeded"},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        # Теперь все чаты хранятся в БД (нет временных)
        is_temporary = False
        
        if not user:
            # Неавторизованный пользователь - сохраняем в БД с anonymous_user
            from apps.anonymousUsageLimits.service import AnonymousUsageLimitService
            
            fingerprint_hash = request.META.get("HTTP_X_FINGERPRINT_HASH")
            anonymous_user = AnonymousUsageLimitService.get_or_create_anonymous_usage_limit(
                ip_address, fingerprint_hash
            )
            
            if chat_id:
                # Продолжаем существующий чат (chat_id уже деобфусцирован через сериализатор)
                try:
                    chat_session = ChatSession.objects.get(id=chat_id, anonymous_user=anonymous_user)
                except (ValueError, Exception):
                    return Response(
                        {"error": "Invalid chat_id format"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                except ChatSession.DoesNotExist:
                    return Response(
                        {"error": "Chat session not found"},
                        status=status.HTTP_404_NOT_FOUND,
                    )
            else:
                # Создаем новый чат для анонима
                chat_session = ChatService.create_chat_session(
                    anonymous_user=anonymous_user, 
                    title=content
                )
            
            db_chat_id = chat_session.id
            public_chat_id = Abfuscator.encode(
                salt=settings.ABFUSCATOR_ID_KEY, value=chat_session.id, min_length=17
            )
            
            # Save user message
            user_message = ChatService.add_message(chat_session, "user", content)
            user_message_id = user_message.uid
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
                chat_session = ChatService.create_chat_session(user=user, title=content)
            
            db_chat_id = chat_session.id
            # Обфусцируем ID для ответа
            public_chat_id = Abfuscator.encode(
                salt=settings.ABFUSCATOR_ID_KEY, value=chat_session.id, min_length=17
            )
            
            # Save user message
            user_message = ChatService.add_message(chat_session, "user", content)
            user_message_id = user_message.uid

        # Если есть активные SSE соединения, отправляем ответ на ВСЕ устройства
        if session_id and hasattr(ChatService, '_sse_queues') and session_id in ChatService._sse_queues:
            connections = ChatService._sse_queues[session_id]
            
            # Отправляем сообщение пользователя на ВСЕ SSE соединения
            user_msg_data = {
                "messageId": user_message_id,
                "chatId": public_chat_id,
                "role": "user",
                "content": content,
                "v": "1"
            }
            for connection in connections:
                connection['queue'].put(user_msg_data)
            
            # Генерируем ID для ответа ассистента
            assistant_message_id = str(uuid.uuid4())
            
            # Отправляем start-generation на ВСЕ SSE соединения
            start_generation_data = {
                "start-generation": {
                    "chatId": public_chat_id,
                    "messageId": assistant_message_id
                }
            }
            for connection in connections:
                connection['queue'].put(start_generation_data)
            
            # Отправляем loading-start
            loading_start_data = {
                "loading-start": {
                    "chatId": public_chat_id
                }
            }
            for connection in connections:
                connection['queue'].put(loading_start_data)
            
            # Запускаем генерацию ответа в отдельном потоке
            import threading
            
            def generate_response():
                try:
                    print(f"[THREAD] Starting generation for message_id={assistant_message_id}, chat_id={db_chat_id}")
                    stream = ChatService.process_chat_stream(
                        user, db_chat_id, content, ip_address, is_temporary, assistant_message_id
                    )
                    chunk_count = 0
                    for chunk in stream:
                        chunk_count += 1
                        if chunk_count == 1:
                            print(f"[THREAD] First chunk received for message_id={assistant_message_id}")
                        if chunk_count % 10 == 0:
                            print(f"[THREAD] Chunk {chunk_count} for message_id={assistant_message_id}")
                        
                        # Подменяем chatId на публичный обфусцированный ID
                        if isinstance(chunk, dict):
                            # Обычные chunk с chatId на верхнем уровне
                            if "chatId" in chunk:
                                chunk["chatId"] = public_chat_id
                            # loading-end с вложенным chatId
                            if "loading-end" in chunk and isinstance(chunk["loading-end"], dict):
                                chunk["loading-end"]["chatId"] = public_chat_id
                        
                        # Отправляем chunk на ВСЕ SSE соединения с этим session_id
                        if session_id in ChatService._sse_queues:
                            for connection in ChatService._sse_queues[session_id]:
                                connection['queue'].put(chunk)
                    
                    print(f"[THREAD] Generation completed. Total chunks: {chunk_count} for message_id={assistant_message_id}")
                    
                    # Отправляем done-generation на ВСЕ SSE соединения
                    done_generation_data = {
                        "done-generation": {
                            "messageId": assistant_message_id,
                            "chatId": public_chat_id
                        }
                    }
                    if session_id in ChatService._sse_queues:
                        for connection in ChatService._sse_queues[session_id]:
                            connection['queue'].put(done_generation_data)
                    
                    # Проверяем остаток токенов после генерации
                    tokens_ended = False
                    if user and user.is_authenticated:
                        from apps.usageLimits.service import UsageLimitService
                        result = UsageLimitService.check_request_limit(user)
                        tokens_ended = not result["can_make_request"]
                    else:
                        from apps.anonymousUsageLimits.service import AnonymousUsageLimitService
                        result = AnonymousUsageLimitService.check_anonymous_request_limit(ip_address)
                        tokens_ended = not result["can_make_request"]
                    
                    # Отправляем end-tokens на ВСЕ SSE соединения
                    end_tokens_data = {
                        "end-tokens": tokens_ended
                    }
                    if session_id in ChatService._sse_queues:
                        for connection in ChatService._sse_queues[session_id]:
                            connection['queue'].put(end_tokens_data)
                except Exception as e:
                    import traceback
                    print(f"[THREAD ERROR] Exception in generate_response for message_id={assistant_message_id}: {e}")
                    traceback.print_exc()
            
            thread = threading.Thread(target=generate_response)
            thread.daemon = True
            thread.start()

        # Return response
        response_data = {
            "messageId": user_message_id,
            "chatId": public_chat_id,
            "isTemporary": False,
        }

        return Response(response_data, status=status.HTTP_200_OK)


class ChatStreamView(views.APIView):
    """
    GET /chat/stream
    Постоянное SSE соединение для получения ответов ассистента
    
    Требуемые заголовки:
        - X-Fingerprint-Hash: Хэш устройства (обязательный)
        - Authorization: Bearer <jwt> (опционально для авторизованных)
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
        # Шаг 3: Проверяем обязательный заголовок X-Fingerprint-Hash
        fingerprint_hash = request.META.get("HTTP_X_FINGERPRINT_HASH")
        if not fingerprint_hash:
            return Response(
                {"error": "X-Fingerprint-Hash header is required"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        initial_chat_id = request.query_params.get("chatId")
        user = request.user if request.user.is_authenticated else None
        ip_address = self.get_client_ip(request)
        
        # Шаг 4-8: Получаем или создаем session_id из БД
        session_id = ChatService.get_or_create_session_id(
            user=user,
            fingerprint_hash=fingerprint_hash,
            ip_address=ip_address
        )
        
        def event_stream():
            """
            Постоянный генератор SSE событий
            Держит соединение открытым и ждет новых сообщений
            """
            import queue
            import threading
            import time
            
            # Создаем очередь для этого конкретного SSE соединения
            message_queue = queue.Queue()
            connection_id = str(uuid.uuid4())  # Уникальный ID подключения
            
            # Флаги для ping-pong механизма
            ping_pong_active = threading.Event()
            ping_pong_active.set()  # Активен по умолчанию
            connection_alive = threading.Event()
            connection_alive.set()  # Соединение живое
            pong_received = threading.Event()
            
            # Инициализируем глобальное хранилище SSE соединений
            if not hasattr(ChatService, '_sse_queues'):
                ChatService._sse_queues = {}
            
            # Добавляем это подключение к списку для данного session_id
            if session_id not in ChatService._sse_queues:
                ChatService._sse_queues[session_id] = []
            
            connection_data = {
                'connection_id': connection_id,
                'queue': message_queue,
                'user': user,
                'fingerprint_hash': fingerprint_hash,
                'ip': ip_address,
                'chat_id': initial_chat_id,
                'created_at': datetime.now(),
                'pong_received': pong_received  # Для ping-pong
            }
            
            ChatService._sse_queues[session_id].append(connection_data)
            
            def ping_pong_monitor():
                """
                Отдельный поток для ping-pong механизма
                Каждые 60 секунд отправляет ping и ждет pong 5 секунд
                """
                while ping_pong_active.is_set() and connection_alive.is_set():
                    time.sleep(60)  # Ждем 60 секунд
                    
                    if not ping_pong_active.is_set():
                        break
                    
                    # Сбрасываем флаг pong
                    pong_received.clear()
                    
                    # Отправляем ping
                    message_queue.put({'type': 'ping', 'timestamp': datetime.now().isoformat()})
                    
                    # Ждем pong 5 секунд
                    if not pong_received.wait(timeout=5):
                        # Pong не получен за 5 секунд → закрываем соединение
                        connection_alive.clear()
                        message_queue.put("CLOSE")
                        break
            
            # Запускаем ping-pong поток
            ping_thread = threading.Thread(target=ping_pong_monitor, daemon=True)
            ping_thread.start()
            
            try:
                # Отправляем начальное сообщение с sessionId
                yield f"data: {json.dumps({'type': 'connected', 'sessionId': session_id})}\n\n"
                
                # Основной цикл - держим соединение открытым
                while connection_alive.is_set():
                    try:
                        # Ждем сообщение из очереди с таймаутом
                        message = message_queue.get(timeout=30)
                        
                        if message == "CLOSE":
                            break
                        
                        # Отправляем сообщение клиенту
                        yield f"data: {json.dumps(message, ensure_ascii=False)}\n\n"
                        
                    except queue.Empty:
                        # Проверяем жив ли connection
                        if not connection_alive.is_set():
                            break
                        # Отправляем heartbeat для поддержания соединения
                        yield f": heartbeat\n\n"
                        
            except GeneratorExit:
                # Соединение закрыто клиентом
                pass
            finally:
                # Останавливаем ping-pong поток
                ping_pong_active.clear()
                connection_alive.clear()
                
                # Очищаем ТОЛЬКО это конкретное подключение
                if session_id in ChatService._sse_queues:
                    ChatService._sse_queues[session_id] = [
                        conn for conn in ChatService._sse_queues[session_id]
                        if conn['connection_id'] != connection_id
                    ]
                    # Если больше нет подключений с этим session_id - удаляем ключ
                    if not ChatService._sse_queues[session_id]:
                        del ChatService._sse_queues[session_id]

        response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response


class ChatPongView(views.APIView):
    """
    POST /chat/pong
    Получение pong ответа от клиента на ping
    """

    permission_classes = [AllowAny]

    def post(self, request):
        """
        Получение pong от клиента
        
        Request body:
            - sessionId (required): SSE session ID
            - connectionId (optional): Connection ID (если клиент знает)
        
        Returns:
            - success: true/false
        """
        session_id = request.data.get("sessionId")
        
        if not session_id:
            return Response(
                {"error": "sessionId is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Находим все соединения с этим session_id и устанавливаем флаг pong
        if hasattr(ChatService, '_sse_queues') and session_id in ChatService._sse_queues:
            connections = ChatService._sse_queues[session_id]
            for connection in connections:
                # Устанавливаем флаг что pong получен
                if 'pong_received' in connection:
                    connection['pong_received'].set()
            
            return Response({"success": True}, status=status.HTTP_200_OK)
        else:
            return Response(
                {"error": "Session not found or already closed"},
                status=status.HTTP_404_NOT_FOUND
            )


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
        
        # Если chatId не передан или null/undefined - возвращаем пустой список
        if not chat_id or chat_id == "null" or chat_id == "undefined":
            return Response({"chatId": None, "messages": []}, status=status.HTTP_200_OK)

        user = request.user if request.user.is_authenticated else None
        public_chat_id = chat_id

        # Get chat history from DB
        try:
            db_chat_id = Abfuscator.decode(salt=settings.ABFUSCATOR_ID_KEY, value=chat_id)
            
            if user:
                # Авторизованный пользователь
                chat_session = ChatSession.objects.get(id=db_chat_id, user=user)
            else:
                # Неавторизованный пользователь - проверяем по fingerprint
                fingerprint_hash = request.META.get("HTTP_X_FINGERPRINT_HASH")
                if not fingerprint_hash:
                    return Response(
                        {"error": "X-Fingerprint-Hash header is required"},
                        status=status.HTTP_403_FORBIDDEN
                    )
                
                # Ищем чат по ID
                chat_session = ChatSession.objects.select_related('anonymous_user').get(id=db_chat_id)
                
                # Проверяем что он принадлежит анонимному пользователю с тем же fingerprint
                if not chat_session.anonymous_user:
                    return Response(
                        {"error": "Chat session not found"}, status=status.HTTP_404_NOT_FOUND
                    )
                
                if chat_session.anonymous_user.fingerprint != fingerprint_hash:
                    return Response(
                        {"error": "Chat session not found"}, status=status.HTTP_404_NOT_FOUND
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
                "v": str(msg.version),
                "createdAt": msg.created_at.isoformat(),
            }
            for msg in history
        ]
        response_data = {"chatId": public_chat_id, "messages": messages}

        return Response(response_data, status=status.HTTP_200_OK)
    
    def get_client_ip(self, request):
        """Get client IP address"""
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0]
        else:
            ip = request.META.get("REMOTE_ADDR")
        return ip


class RegenerationView(views.APIView):
    """
    POST /api/regeneration
    Регенерировать сообщение ассистента с инкрементом версии.
    Ожидает поля: messageId (uid сообщения ассистента), sessionId (для SSE)
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
        message_id = request.data.get("messageId")
        session_id = request.data.get("sessionId")

        if not message_id:
            return Response({"error": "messageId is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not session_id:
            return Response({"error": "sessionId is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Verify user
        user = request.user if request.user.is_authenticated else None
        ip_address = self.get_client_ip(request)

        # Find target message
        try:
            target_message = Message.objects.select_related('chat_session').get(uid=message_id)
        except Message.DoesNotExist:
            return Response({"error": "Message not found"}, status=status.HTTP_404_NOT_FOUND)

        chat_session = target_message.chat_session

        # Verify ownership
        if user:
            if chat_session.user != user:
                return Response({"error": "Access denied"}, status=status.HTTP_403_FORBIDDEN)
        else:
            # Неавторизованный пользователь
            fingerprint_hash = request.META.get("HTTP_X_FINGERPRINT_HASH")
            if not fingerprint_hash:
                return Response(
                    {"error": "X-Fingerprint-Hash header is required"},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            if not chat_session.anonymous_user or chat_session.anonymous_user.fingerprint != fingerprint_hash:
                return Response({"error": "Access denied"}, status=status.HTTP_403_FORBIDDEN)

        # Only assistant messages can be regenerated
        if target_message.role != "assistant":
            return Response({"error": "Can only regenerate assistant messages"}, status=status.HTTP_400_BAD_REQUEST)

        # Остановка активного стриминга, если он идёт
        db_chat_id = chat_session.id
        if db_chat_id in ChatService._streaming_control:
            ChatService._streaming_control[db_chat_id]["should_continue"] = False
            print(f"[REGENERATION] Stopped active streaming for chat_id={db_chat_id}")
            # Даём время на корректное завершение стриминга
            import time
            time.sleep(0.1)

        # Delete all messages after target message (не включая сам target_message)
        Message.objects.filter(
            chat_session=chat_session,
            created_at__gt=target_message.created_at,
        ).delete()

        # Increment version and save immediately to avoid race conditions
        new_version = target_message.version + 1
        target_message.version = new_version
        target_message.save(update_fields=['version'])

        # Get history up to target message (exclusive)
        history = Message.objects.filter(
            chat_session=chat_session,
            created_at__lt=target_message.created_at,
        ).order_by("created_at")

        # Prepare messages for LLM
        api_messages = [{"role": msg.role, "content": msg.content} for msg in history]

        # Start streaming with new version through ChatService
        # We'll use threading like in ChatMessagesView
        import threading
        
        def generate_response():
            try:
                print(f"[REGENERATION] Starting regeneration for message_id={message_id}, new_version={new_version}")
                
                # Get LLM client and get full response
                client = ChatService.get_llm_client()
                from service.llm.async_loop import run_async
                response = run_async(client.chat(api_messages, stream=False))
                
                if "error" in response:
                    llm_error = response["error"]
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"LLM Error during regeneration: {llm_error}, messageId: {message_id}")
                    
                    # Send error to SSE
                    if session_id in ChatService._sse_queues:
                        error_data = {
                            "error": llm_error,
                            "messageId": message_id,
                            "chatId": Abfuscator.encode(salt=settings.ABFUSCATOR_ID_KEY, value=chat_session.id, min_length=17),
                        }
                        for connection in ChatService._sse_queues[session_id]:
                            connection['queue'].put(error_data)
                    return
                
                # Extract response content
                choices = response.get("choices", [])
                if not choices:
                    return
                
                message_obj = choices[0].get("message", {})
                full_content = message_obj.get("content", "")
                
                if not full_content:
                    return
                
                # Update message in DB with new content (version already saved)
                # Get fresh object from DB in this thread
                msg_to_update = Message.objects.get(uid=message_id)
                msg_to_update.content = full_content
                msg_to_update.save(update_fields=['content'])
                
                print(f"[REGENERATION] Updated message {message_id} to version {new_version}")
                
                # Send loading-end
                public_chat_id = Abfuscator.encode(salt=settings.ABFUSCATOR_ID_KEY, value=chat_session.id, min_length=17)
                if session_id in ChatService._sse_queues:
                    loading_end_data = {
                        "loading-end": {
                            "chatId": public_chat_id
                        }
                    }
                    for connection in ChatService._sse_queues[session_id]:
                        connection['queue'].put(loading_end_data)
                
                # Stream chunks with new version
                chunk_size = settings.STREAMING_CHUNK_SIZE
                chunk_delay = settings.STREAMING_CHUNK_DELAY
                accumulated_content = ""
                
                for i in range(0, len(full_content), chunk_size):
                    chunk_text = full_content[i:i + chunk_size]
                    accumulated_content += chunk_text
                    
                    if session_id in ChatService._sse_queues:
                        chunk_data = {
                            "messageId": message_id,
                            "chatId": public_chat_id,
                            "role": "assistant",
                            "content": accumulated_content,
                            "v": str(new_version),
                            "resolveMessage": False,
                        }
                        for connection in ChatService._sse_queues[session_id]:
                            connection['queue'].put(chunk_data)
                    
                    if chunk_delay > 0:
                        import time
                        time.sleep(chunk_delay)
                
                # Send final message with resolveMessage
                if session_id in ChatService._sse_queues:
                    final_data = {
                        "messageId": message_id,
                        "chatId": public_chat_id,
                        "role": "assistant",
                        "content": full_content,
                        "v": str(new_version),
                        "resolveMessage": ChatService.should_show_resolve_message(user),
                    }
                    for connection in ChatService._sse_queues[session_id]:
                        connection['queue'].put(final_data)
                
                # Send done-generation
                if session_id in ChatService._sse_queues:
                    done_data = {
                        "done-generation": {
                            "messageId": message_id,
                            "chatId": public_chat_id
                        }
                    }
                    for connection in ChatService._sse_queues[session_id]:
                        connection['queue'].put(done_data)
                
                # Проверяем остаток токенов после генерации
                tokens_ended = False
                if user and user.is_authenticated:
                    from apps.usageLimits.service import UsageLimitService
                    result = UsageLimitService.check_request_limit(user)
                    tokens_ended = not result["can_make_request"]
                else:
                    from apps.anonymousUsageLimits.service import AnonymousUsageLimitService
                    result = AnonymousUsageLimitService.check_anonymous_request_limit(ip_address)
                    tokens_ended = not result["can_make_request"]
                
                # Send end-tokens
                if session_id in ChatService._sse_queues:
                    end_tokens_data = {
                        "end-tokens": tokens_ended
                    }
                    for connection in ChatService._sse_queues[session_id]:
                        connection['queue'].put(end_tokens_data)
                
                print(f"[REGENERATION] Completed regeneration for message_id={message_id}")
                
            except Exception as e:
                import traceback
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Error during regeneration: {str(e)}, messageId: {message_id}")
                traceback.print_exc()
        
        # Send start-generation and loading-start immediately
        if session_id and hasattr(ChatService, '_sse_queues') and session_id in ChatService._sse_queues:
            public_chat_id = Abfuscator.encode(salt=settings.ABFUSCATOR_ID_KEY, value=chat_session.id, min_length=17)
            
            # Отправляем start-generation (как в обычной отправке)
            start_generation_data = {
                "start-generation": {
                    "chatId": public_chat_id,
                    "messageId": message_id
                }
            }
            for connection in ChatService._sse_queues[session_id]:
                connection['queue'].put(start_generation_data)
            
            # Отправляем loading-start
            loading_start_data = {
                "loading-start": {
                    "chatId": public_chat_id
                }
            }
            for connection in ChatService._sse_queues[session_id]:
                connection['queue'].put(loading_start_data)
        
        # Start generation in separate thread
        thread = threading.Thread(target=generate_response)
        thread.daemon = True
        thread.start()
        
        return Response(
            {
                "success": True,
                "message": "Regeneration started",
                "messageId": message_id,
                "newVersion": new_version
            },
            status=status.HTTP_200_OK
        )


class ChatRenameView(views.APIView):
    """
    PUT /chat/rename
    Переименовать чат
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
    
    def put(self, request):
        """
        Переименовать чат
        
        Request body:
            - chatId (required): Обфусцированный ID чата
            - title (required): Новое название чата
        
        Returns:
            - chatId: ID чата
            - title: Новое название
        """
        chat_id = request.data.get("chatId")
        title = request.data.get("title")
        
        if not chat_id:
            return Response(
                {"error": "chatId is required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not title:
            return Response(
                {"error": "title is required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Деобфусцируем chatId
        try:
            db_chat_id = Abfuscator.decode(salt=settings.ABFUSCATOR_ID_KEY, value=chat_id)
        except (ValueError, Exception):
            return Response(
                {"error": "Invalid chatId format"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        user = request.user if request.user.is_authenticated else None
        
        # Проверяем ownership чата
        try:
            if user:
                # Авторизованный пользователь
                chat_session = ChatSession.objects.get(id=db_chat_id, user=user)
            else:
                # Неавторизованный пользователь - проверяем по fingerprint
                fingerprint_hash = request.META.get("HTTP_X_FINGERPRINT_HASH")
                if not fingerprint_hash:
                    return Response(
                        {"error": "X-Fingerprint-Hash header is required"},
                        status=status.HTTP_403_FORBIDDEN
                    )
                
                # Ищем чат по ID
                chat_session = ChatSession.objects.select_related('anonymous_user').get(id=db_chat_id)
                
                # Проверяем что он принадлежит анонимному пользователю с тем же fingerprint
                if not chat_session.anonymous_user:
                    return Response(
                        {"error": "Chat session not found"}, 
                        status=status.HTTP_404_NOT_FOUND
                    )
                
                if chat_session.anonymous_user.fingerprint != fingerprint_hash:
                    return Response(
                        {"error": "Chat session not found"}, 
                        status=status.HTTP_404_NOT_FOUND
                    )
        except ChatSession.DoesNotExist:
            return Response(
                {"error": "Chat session not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Обновляем title
        # Обрезаем до 255 символов если слишком длинный
        if len(title) > 255:
            title = title[:252] + "..."
        
        chat_session.title = title
        chat_session.created_at = timezone.now()
        chat_session.updated_at = timezone.now()
        chat_session.save(update_fields=['title', 'created_at', 'updated_at'])
        
        # Возвращаем обновленные данные
        return Response(
            {
                "chatId": chat_id,
                "title": chat_session.title
            },
            status=status.HTTP_200_OK
        )


class ChatStopStreamingView(views.APIView):
    """
    POST /chat/stop-streaming
    Остановить стриминг сообщения для текущего чата
    """
    
    permission_classes = [AllowAny]
    
    def post(self, request):
        """
        Остановить стриминг сообщения
        
        Request body:
            - sessionId (required): ID SSE сессии
            - chatId (required): Обфусцированный ID чата
        
        Returns:
            - success: True если стриминг остановлен
            - message: Сообщение о результате
        """
        session_id = request.data.get("sessionId")
        chat_id = request.data.get("chatId")
        
        if not session_id:
            return Response(
                {"error": "sessionId is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not chat_id:
            return Response(
                {"error": "chatId is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Деобфусцируем chatId
        try:
            db_chat_id = Abfuscator.decode(salt=settings.ABFUSCATOR_ID_KEY, value=chat_id)
        except (ValueError, Exception):
            return Response(
                {"error": "Invalid chatId format"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Проверяем что стриминг активен для этого чата
        if db_chat_id not in ChatService._streaming_control:
            return Response(
                {
                    "success": False,
                    "message": "No active streaming found for this chat"
                },
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Устанавливаем флаг остановки
        ChatService._streaming_control[db_chat_id]["should_continue"] = False
        print(f"[STOP-STREAMING] Stopping streaming for chat_id={db_chat_id}, session_id={session_id}")
        
        return Response(
            {
                "success": True,
                "message": "Streaming stop requested"
            },
            status=status.HTTP_200_OK
        )