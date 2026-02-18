"""
Persistent SSE connection for chat
Поддерживает постоянное SSE соединение для обмена сообщениями
"""
import json
import uuid
import asyncio
import threading
import queue
from datetime import datetime
from django.conf import settings
from django.http import StreamingHttpResponse
from rest_framework import views, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.ChatSessions.models import ChatSession
from apps.messages.models import Message
from service.obfuscation import Abfuscator
from .services import ChatService


# Глобальное хранилище для SSE соединений
SSE_CONNECTIONS = {}


class PersistentChatStreamView(views.APIView):
    """
    GET /chat/persistent-stream
    Постоянное SSE соединение для чата
    Соединение держится открытым постоянно для непрерывного общения
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
        Постоянное SSE соединение для чата
        
        Query params:
            - sessionId (optional): ID сессии для восстановления соединения
        
        Это соединение остается открытым постоянно.
        Сообщения отправляются через /chat/messages, а ответы приходят через это SSE соединение.
        """
        user = request.user if request.user.is_authenticated else None
        ip_address = self.get_client_ip(request)
        
        # Создаем или восстанавливаем сессию
        session_id = request.query_params.get("sessionId") or str(uuid.uuid4())
        
        def event_stream():
            """
            Генератор для постоянного SSE соединения
            Держит соединение открытым и обрабатывает сообщения
            """
            # Создаем очередь для этого соединения
            message_queue = queue.Queue()
            SSE_CONNECTIONS[session_id] = {
                'queue': message_queue,
                'user': user,
                'ip': ip_address,
                'created_at': datetime.now()
            }
            
            try:
                # Отправляем начальное подтверждение соединения
                yield f"data: {json.dumps({'type': 'connected', 'sessionId': session_id})}\n\n"
                
                # Основной цикл обработки сообщений
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
                        # Используем комментарий SSE, чтобы не отправлять данные
                        yield f": heartbeat\n\n"
                        
            except GeneratorExit:
                # Соединение закрыто клиентом
                pass
            finally:
                # Очищаем соединение при закрытии
                if session_id in SSE_CONNECTIONS:
                    del SSE_CONNECTIONS[session_id]
        
        response = StreamingHttpResponse(
            event_stream(),
            content_type="text/event-stream"
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response


class PersistentChatMessagesView(views.APIView):
    """
    POST /chat/persistent-messages
    Отправка сообщений через постоянное SSE соединение
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
    
    @staticmethod
    def _resolve_parent(parent_id, chat_session):
        """Resolve parent message from parentId or fall back to current_node."""
        if parent_id:
            try:
                return Message.objects.get(uid=parent_id, chat_session=chat_session)
            except Message.DoesNotExist:
                return None
        if chat_session.current_node:
            return chat_session.current_node
        return None

    def post(self, request):
        """
        Отправляет сообщение и стримит ответ через активное SSE соединение
        
        Request body:
            - sessionId: ID SSE сессии (обязательно)
            - content: Текст сообщения (обязательно)
            - chatId: ID чата (опционально, для продолжения чата)
            - parentId: uid родительского сообщения (опционально)
        """
        session_id = request.data.get("sessionId")
        content = request.data.get("content")
        chat_id = request.data.get("chatId")
        parent_id = request.data.get("parentId")
        
        if not session_id:
            return Response(
                {"error": "sessionId is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not content:
            return Response(
                {"error": "content is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Получаем SSE соединение
        connection = SSE_CONNECTIONS.get(session_id)
        if not connection:
            return Response(
                {"error": "SSE session not found. Please establish SSE connection first."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        message_queue = connection['queue']
        user = request.user if request.user.is_authenticated else None
        ip_address = self.get_client_ip(request)
        
        # Проверяем лимиты
        can_proceed, error_msg = ChatService.check_usage_limits(user, ip_address)
        if not can_proceed:
            # Отправляем ошибку через SSE
            message_queue.put({
                "error": error_msg or "Request limit exceeded",
                "messageId": str(uuid.uuid4()),
                "chatId": chat_id or "",
                "type": "error"
            })
            return Response(
                {"error": error_msg},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )
        
        # Теперь все чаты хранятся в БД (нет временных)
        is_temporary = False
        
        # Создаем или получаем chat_id
        if not user:
            # Неавторизованный пользователь - сохраняем в БД с anonymous_user
            from apps.anonymousUsageLimits.service import AnonymousUsageLimitService
            
            fingerprint_hash = request.META.get("HTTP_X_FINGERPRINT_HASH")
            anonymous_user = AnonymousUsageLimitService.get_or_create_anonymous_usage_limit(
                ip_address, fingerprint_hash
            )
            
            if chat_id:
                # Продолжаем существующий чат - деобфусцируем ID
                try:
                    db_chat_id = Abfuscator.decode(salt=settings.ABFUSCATOR_ID_KEY, value=chat_id)
                    chat_session = ChatSession.objects.get(id=db_chat_id, anonymous_user=anonymous_user)
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
            
            # Resolve parent message for branching
            parent_message = self._resolve_parent(parent_id, chat_session)
            
            # Сохраняем сообщение пользователя
            user_message = ChatService.add_message(chat_session, "user", content, parent=parent_message)
            user_message_id = user_message.uid
        else:
            # Авторизованный пользователь
            if chat_id:
                # Деобфусцируем для работы с БД
                try:
                    db_chat_id = Abfuscator.decode(salt=settings.ABFUSCATOR_ID_KEY, value=chat_id)
                    chat_session = ChatSession.objects.get(id=db_chat_id, user=user)
                except (ValueError, Exception):
                    return Response(
                        {"error": "Invalid chat_id format"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                except ChatSession.DoesNotExist:
                    return Response(
                        {"error": "Chat session not found"},
                        status=status.HTTP_404_NOT_FOUND
                    )
            else:
                # Создаем новый чат
                chat_session = ChatService.create_chat_session(user=user, title=content)
                db_chat_id = chat_session.id
            
            # Обфусцируем для клиента
            public_chat_id = Abfuscator.encode(
                salt=settings.ABFUSCATOR_ID_KEY, value=db_chat_id, min_length=17
            )
            
            # Resolve parent message for branching
            parent_message = self._resolve_parent(parent_id, chat_session)
            
            # Сохраняем сообщение пользователя
            user_message = ChatService.add_message(chat_session, "user", content, parent=parent_message)
            user_message_id = user_message.uid
        
        # Отправляем подтверждение о создании сообщения через SSE
        message_queue.put({
            "type": "userMessage",
            "messageId": user_message_id,
            "chatId": public_chat_id,
            "role": "user",
            "content": content,
            "v": "1",
            "isTemporary": False,
            "parentId": user_message.parent.uid if user_message.parent else None,
            "currentVersion": user_message.current_version,
            "totalVersions": user_message.total_versions,
        })
        
        # Отправляем loading-start
        message_queue.put({
            "loading-start": {
                "chatId": public_chat_id
            }
        })
        
        # Запускаем генерацию ответа в отдельном потоке
        def generate_response():
            try:
                # Используем существующий сервис для генерации
                stream = ChatService.process_chat_stream(
                    user, db_chat_id, content, ip_address, is_temporary,
                    parent_message=user_message,
                )
                
                for chunk in stream:
                    # Подменяем chatId на публичный обфусцированный ID
                    if isinstance(chunk, dict):
                        # Обычные chunk с chatId на верхнем уровне
                        if "chatId" in chunk:
                            chunk["chatId"] = public_chat_id
                        # loading-end с вложенным chatId
                        if "loading-end" in chunk and isinstance(chunk["loading-end"], dict):
                            chunk["loading-end"]["chatId"] = public_chat_id
                    message_queue.put(chunk)
                    
            except Exception as e:
                import traceback
                traceback.print_exc()
                message_queue.put({
                    "type": "error",
                    "error": f"Error generating response: {str(e)}",
                    "messageId": str(uuid.uuid4()),
                    "chatId": public_chat_id
                })
        
        # Запускаем в отдельном потоке
        thread = threading.Thread(target=generate_response)
        thread.daemon = True
        thread.start()
        
        # Возвращаем немедленный ответ
        return Response({
            "messageId": user_message_id,
            "chatId": public_chat_id,
            "isTemporary": is_temporary,
            "status": "processing",
            "parentId": user_message.parent.uid if user_message.parent else None,
            "currentVersion": user_message.current_version,
            "totalVersions": user_message.total_versions,
        })
