import uuid
from datetime import date, datetime
from typing import Any, Generator, Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction

from apps.ChatSessions.models import ChatSession
from apps.messages.models import Message
from apps.usageLimits.service import UsageLimitService
from apps.anonymousUsageLimits.service import AnonymousUsageLimitService
from apps.anonymousUsageLimits.models import AnonymousUsageLimit
from service.llm.client import LLMClient
from service.llm.sentx_provider import SentXProvider
from service.obfuscation import Abfuscator

User = get_user_model()


class ChatService:
    """Service for handling chat operations"""

    # In-memory storage for temporary chat sessions (for anonymous users)
    _temporary_sessions = {}
    
    @staticmethod
    def get_or_create_session_id(
        user: Optional[User],
        fingerprint_hash: str,
        ip_address: str
    ) -> str:
        """
        Получить или создать session_id из БД
        
        Логика:
        - Для авторизованных: ищем/создаем ChatSession с session_id
        - Для неавторизованных: ищем/создаем AnonymousUsageLimit с session_id
        
        Args:
            user: User объект или None
            fingerprint_hash: Хэш устройства
            ip_address: IP адрес
            
        Returns:
            session_id строка
        """
        if user:
            # Шаг 2: Авторизованный пользователь
            # Проверяем есть ли у пользователя session_id в БД
            if user.session_id:
                # Есть существующий session_id - возвращаем его
                return user.session_id
            else:
                # Генерируем новый уникальный session_id
                session_id = ChatService._generate_unique_session_id()
                
                # Сохраняем в User
                user.session_id = session_id
                user.save(update_fields=['session_id'])
                
                return session_id
        else:
            # Шаг 4-6: Неавторизованный пользователь
            today = date.today()
            
            # Ищем по fingerprint_hash
            anonymous_limit = AnonymousUsageLimit.objects.filter(
                fingerprint=fingerprint_hash,
                last_reset_date=today
            ).first()
            
            if anonymous_limit:
                # Найдена запись
                if anonymous_limit.session_id:
                    # Есть session_id - возвращаем
                    return anonymous_limit.session_id
                else:
                    # Нет session_id - генерируем
                    session_id = ChatService._generate_unique_session_id()
                    anonymous_limit.session_id = session_id
                    anonymous_limit.save(update_fields=['session_id'])
                    return session_id
            else:
                # Создаем новую запись
                session_id = ChatService._generate_unique_session_id()
                AnonymousUsageLimit.objects.create(
                    fingerprint=fingerprint_hash,
                    session_id=session_id,
                    ip_address=ip_address,
                    requests_made_today=0,
                    last_reset_date=today
                )
                return session_id
    
    @staticmethod
    def _generate_unique_session_id() -> str:
        """
        Генерирует уникальный session_id
        Проверяет что он не занят в User и AnonymousUsageLimit
        """
        while True:
            session_id = str(uuid.uuid4())
            
            # Проверяем уникальность в обеих таблицах
            exists_in_user = User.objects.filter(session_id=session_id).exists()
            exists_in_anon = AnonymousUsageLimit.objects.filter(session_id=session_id).exists()
            
            if not exists_in_user and not exists_in_anon:
                return session_id

    @staticmethod
    def get_llm_client() -> LLMClient:
        """Get configured LLM client"""
        provider = SentXProvider()
        return LLMClient(provider)

    @staticmethod
    @transaction.atomic
    def create_chat_session(user: Optional[User] = None, title: str = "") -> ChatSession:
        """Create a new chat session"""
        return ChatSession.objects.create(user=user, title=title)

    @staticmethod
    def get_or_create_temporary_session(temp_chat_id: str) -> dict:
        """
        Get or create a temporary chat session for anonymous users

        Args:
            temp_chat_id: Temporary chat ID

        Returns:
            Temporary session dict with messages list
        """
        if temp_chat_id not in ChatService._temporary_sessions:
            ChatService._temporary_sessions[temp_chat_id] = {
                "messages": [],
                "created_at": datetime.now(),
            }
        return ChatService._temporary_sessions[temp_chat_id]

    @staticmethod
    @transaction.atomic
    def add_message(
        chat_session: ChatSession, role: str, content: str, message_uid: Optional[uuid.UUID] = None
    ) -> Message:
        """Add a message to a chat session"""
        if message_uid is None:
            message_uid = uuid.uuid4()

        return Message.objects.create(
            chat_session=chat_session, role=role, content=content, uid=str(message_uid)
        )

    @staticmethod
    def add_temporary_message(temp_session: dict, role: str, content: str, message_id: str):
        """Add a message to a temporary session"""
        temp_session["messages"].append(
            {
                "messageId": message_id,
                "role": role,
                "content": content,
                "createdAt": datetime.now().isoformat(),
            }
        )

    @staticmethod
    def get_chat_history(chat_session: ChatSession, limit: int = 100) -> list[Message]:
        """Get chat history (last N messages)"""
        return list(chat_session.messages.order_by("-created_at")[:limit][::-1])

    @staticmethod
    def get_temporary_chat_history(temp_chat_id: str, limit: int = 100) -> list[dict]:
        """Get temporary chat history"""
        temp_session = ChatService._temporary_sessions.get(temp_chat_id, {})
        messages = temp_session.get("messages", [])
        return messages[-limit:]

    @staticmethod
    def check_usage_limits(user: Optional[User], ip_address: str) -> tuple[bool, Optional[str]]:
        """
        Check usage limits for user or anonymous

        Returns:
            (is_allowed, error_message)
        """
        if user and user.is_authenticated:
            # Check user limits
            usage_limit = UsageLimitService.get_or_create_usage_limit(user)
            can_proceed, error_msg = UsageLimitService.check_request_limit(user)
            if not can_proceed:
                return False, error_msg
            return True, None
        else:
            # Check anonymous limits
            anon_limit = AnonymousUsageLimitService.get_or_create_anonymous_usage_limit(
                ip_address
            )
            result = AnonymousUsageLimitService.check_anonymous_request_limit(
                ip_address
            )
            can_proceed = result["can_make_request"]
            if not can_proceed:
                return False, f"Daily limit exceeded. Requests left: {result['requests_left']}"
            return True, None

    @staticmethod
    def increment_usage(user: Optional[User], ip_address: str):
        """Increment usage count for user or anonymous"""
        if user and user.is_authenticated:
            UsageLimitService.increment_request_count(user)
        else:
            AnonymousUsageLimitService.increment_anonymous_request_count(ip_address)

    @staticmethod
    def should_show_resolve_message(user: Optional[User]) -> bool:
        """
        Determine if we should show resolve message (subscription modal)

        Returns:
            True if user should be prompted to subscribe
        """
        if not user or not user.is_authenticated:
            # Anonymous users always see resolve message
            return True

        if user.is_unlimited:
            # Unlimited users never see resolve message
            return False

        # Check if user has active subscription
        if hasattr(user, "subscription") and user.subscription:
            from apps.payments.models import Subscription

            if user.subscription.status == Subscription.Status.ACTIVE:
                return False

        # Free users see resolve message
        return True

    @staticmethod
    def process_chat_stream(
        user: Optional[User],
        chat_id: Optional[str],
        content: str,
        ip_address: str,
        is_temporary: bool = False,
        assistant_message_id: Optional[str] = None,
    ) -> Generator[dict[str, Any], None, None]:
        """
        Process a chat message and stream the response

        Args:
            user: User object (None for anonymous)
            chat_id: Chat ID (permanent or temporary)
            content: User message content
            ip_address: User's IP address
            is_temporary: Whether this is a temporary session

        Yields:
            SSE message chunks
        """
        # Check usage limits
        can_proceed, error_msg = ChatService.check_usage_limits(user, ip_address)
        if not can_proceed:
            yield {
                "error": error_msg or "Request limit exceeded",
                "messageId": str(uuid.uuid4()),
                "chatId": chat_id or "",
            }
            return

        # Get or create chat session
        if is_temporary:
            temp_session = ChatService.get_or_create_temporary_session(chat_id)
            user_message_id = str(uuid.uuid4())
            ChatService.add_temporary_message(temp_session, "user", content, user_message_id)
            
            # Build messages for LLM
            messages = [
                {"role": msg["role"], "content": msg["content"]}
                for msg in temp_session["messages"]
            ]
        else:
            # Permanent session
            if chat_id:
                try:
                    if user:
                        chat_session = ChatSession.objects.get(id=chat_id, user=user)
                    else:
                        yield {"error": "Unauthorized", "messageId": "", "chatId": ""}
                        return
                except ChatSession.DoesNotExist:
                    yield {"error": "Chat session not found", "messageId": "", "chatId": ""}
                    return
            else:
                # Create new session
                chat_session = ChatService.create_chat_session(user)
                chat_id = str(chat_session.id)

            # Save user message
            user_message = ChatService.add_message(chat_session, "user", content)
            user_message_id = user_message.uid

            # Get chat history for context
            history = ChatService.get_chat_history(chat_session, limit=100)
            messages = [{"role": msg.role, "content": msg.content} for msg in history]

        # Get LLM client and stream response
        client = ChatService.get_llm_client()
        # Используем переданный ID или генерируем новый
        if not assistant_message_id:
            assistant_message_id = str(uuid.uuid4())
        
        full_content = ""

        try:
            stream = client.chat(messages, stream=True)
            
            for chunk in stream:
                # Check for errors
                if "error" in chunk:
                    yield {
                        "error": chunk["error"],
                        "messageId": assistant_message_id,
                        "chatId": chat_id,
                    }
                    return

                # Extract content from chunk
                choices = chunk.get("choices", [])
                if not choices:
                    continue

                delta = choices[0].get("delta", {})
                content_part = delta.get("content")

                if content_part:
                    full_content += content_part

                    # Yield SSE message with accumulated content
                    yield {
                        "messageId": assistant_message_id,
                        "chatId": chat_id,
                        "role": "assistant",
                        "content": full_content,  # Всегда отправляем полный накопленный контент
                        "resolveMessage": False,  # Will set to True in final message
                    }

            # Save assistant message
            if is_temporary:
                ChatService.add_temporary_message(
                    temp_session, "assistant", full_content, assistant_message_id
                )
            else:
                ChatService.add_message(
                    chat_session, "assistant", full_content, uuid.UUID(assistant_message_id)
                )

            # Increment usage count
            ChatService.increment_usage(user, ip_address)

            # Send final message with resolveMessage flag
            yield {
                "messageId": assistant_message_id,
                "chatId": chat_id,
                "role": "assistant",
                "content": full_content,
                "resolveMessage": ChatService.should_show_resolve_message(user),
            }

        except Exception as e:
            import traceback

            traceback.print_exc()
            yield {
                "error": f"Error processing request: {str(e)}",
                "messageId": assistant_message_id,
                "chatId": chat_id,
            }

