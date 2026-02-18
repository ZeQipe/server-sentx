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
    
    # Глобальное хранилище для контроля стриминга
    # Ключ: chat_id (str), Значение: dict с информацией о стриминге
    _streaming_control = {}
    
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
    def create_chat_session(
        user: Optional[User] = None, 
        anonymous_user = None,
        title: str = ""
    ) -> ChatSession:
        """Create a new chat session for authorized or anonymous user"""
        return ChatSession.objects.create(
            user=user,
            anonymous_user=anonymous_user,
            title=title
        )

    @staticmethod
    @transaction.atomic
    def add_message(
        chat_session: ChatSession,
        role: str,
        content: str,
        parent: Optional[Message] = None,
        message_uid: Optional[uuid.UUID] = None,
        version: int = 1,
    ) -> Message:
        """
        Add a message to a chat session with branching support.

        Automatically computes current_version / total_versions among siblings,
        updates parent.active_child and chat_session.current_node.
        """
        if message_uid is None:
            message_uid = uuid.uuid4()

        sibling_count = Message.objects.filter(
            parent=parent, chat_session=chat_session, role=role
        ).count()

        new_version = sibling_count + 1

        msg = Message.objects.create(
            chat_session=chat_session,
            role=role,
            content=content,
            uid=str(message_uid),
            version=version,
            parent=parent,
            current_version=new_version,
            total_versions=new_version,
        )

        if sibling_count > 0:
            Message.objects.filter(
                parent=parent, chat_session=chat_session, role=role
            ).exclude(pk=msg.pk).update(total_versions=new_version)

        if parent is not None:
            parent.active_child = msg
            parent.save(update_fields=["active_child"])

        chat_session.current_node = msg
        chat_session.save(update_fields=["current_node"])

        return msg

    @staticmethod
    def get_chat_history(chat_session: ChatSession, limit: int = 100) -> list[Message]:
        """Legacy: get chat history as flat list (fallback)."""
        return list(chat_session.messages.order_by("-created_at")[:limit][::-1])

    @staticmethod
    def get_active_branch(chat_session: ChatSession) -> list[Message]:
        """
        Walk from current_node up to root via parent pointers.
        Returns messages in chronological order (root first).
        current_version / total_versions are already stored on each message.
        """
        path: list[Message] = []
        node = chat_session.current_node
        while node is not None:
            path.append(node)
            node = node.parent
        path.reverse()
        return path

    @staticmethod
    def get_active_branch_for_llm(parent_message: Message) -> list[dict[str, str]]:
        """
        Build the LLM context by walking up from *parent_message* to root.
        Returns list of {"role": ..., "content": ...} in chronological order.
        """
        path: list[dict[str, str]] = []
        node: Optional[Message] = parent_message
        while node is not None:
            path.append({"role": node.role, "content": node.content})
            node = node.parent
        path.reverse()
        return path

    @staticmethod
    @transaction.atomic
    def switch_branch(chat_session: ChatSession, target_message_uid: str) -> list[Message]:
        """
        Switch the active branch to the sibling identified by *target_message_uid*.

        1. Update parent.active_child to target.
        2. Walk down via active_child to the leaf.
        3. Set chat_session.current_node = leaf.
        4. Return the new active branch.
        """
        target = Message.objects.select_related("parent").get(
            uid=target_message_uid, chat_session=chat_session
        )

        if target.parent is not None:
            target.parent.active_child = target
            target.parent.save(update_fields=["active_child"])

        node = target
        while node.active_child is not None:
            node = node.active_child

        chat_session.current_node = node
        chat_session.save(update_fields=["current_node"])

        return ChatService.get_active_branch(chat_session)

    @staticmethod
    def get_siblings_info(message: Message) -> dict:
        """
        Return branching metadata for a message.
        current_version and total_versions are read directly from the instance.
        siblings list is fetched only when needed (e.g. switch-branch).
        """
        siblings = list(
            Message.objects.filter(
                parent=message.parent,
                chat_session=message.chat_session,
                role=message.role,
            )
            .order_by("created_at")
            .values_list("uid", flat=True)
        )
        return {
            "currentVersion": message.current_version,
            "totalVersions": message.total_versions,
            "siblings": siblings,
        }

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
            result = UsageLimitService.check_request_limit(user)
            can_proceed = result["can_make_request"]
            if not can_proceed:
                return False, f"Daily limit exceeded. Requests left: {result['requests_left']}"
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
        version: int = 1,
        parent_message: Optional[Message] = None,
    ) -> Generator[dict[str, Any], None, None]:
        """
        Process a chat message and stream the response.

        Args:
            user: User object (None for anonymous)
            chat_id: Chat ID (db id)
            content: User message content
            ip_address: User's IP address
            is_temporary: Whether this is a temporary session
            assistant_message_id: Pre-generated uid for the assistant message
            version: Legacy version field value
            parent_message: The user message that acts as parent for the assistant reply.
                            Used to build branch-aware LLM context.

        Yields:
            SSE message chunks
        """
        can_proceed, error_msg = ChatService.check_usage_limits(user, ip_address)
        if not can_proceed:
            yield {
                "error": error_msg or "Request limit exceeded",
                "messageId": str(uuid.uuid4()),
                "chatId": chat_id or "",
            }
            return

        if chat_id:
            try:
                chat_session = ChatSession.objects.get(id=chat_id)
            except ChatSession.DoesNotExist:
                yield {"error": "Chat session not found", "messageId": "", "chatId": ""}
                return
        else:
            yield {"error": "Chat session ID is required", "messageId": "", "chatId": ""}
            return

        # Build LLM context from the active branch
        if parent_message is not None:
            messages = ChatService.get_active_branch_for_llm(parent_message)
        else:
            # Fallback: legacy flat history
            from django.conf import settings as _s
            history = ChatService.get_chat_history(chat_session, limit=_s.CHAT_HISTORY_LIMIT)
            messages = [{"role": msg.role, "content": msg.content} for msg in history]

        client = ChatService.get_llm_client()
        if not assistant_message_id:
            assistant_message_id = str(uuid.uuid4())

        ChatService._streaming_control[chat_id] = {
            "should_continue": True,
            "message_id": assistant_message_id,
            "started_at": datetime.now(),
        }

        full_content = ""
        generation_completed = False
        streaming_stopped = False
        assistant_msg: Optional[Message] = None

        try:
            print(f"[SERVICE] Calling async LLM client for message_id={assistant_message_id}")
            from service.llm.async_loop import run_async
            response = run_async(client.chat(messages, stream=False))
            print(f"[SERVICE] LLM response received for message_id={assistant_message_id}")

            if "error" in response:
                import logging
                logging.getLogger(__name__).error(
                    f"LLM Error: {response['error']}, messageId: {assistant_message_id}, chatId: {chat_id}"
                )
                yield {"error": response["error"], "messageId": assistant_message_id, "chatId": chat_id}
                return

            choices = response.get("choices", [])
            if not choices:
                yield {"error": "No response from LLM", "messageId": assistant_message_id, "chatId": chat_id}
                return

            msg_obj = choices[0].get("message", {})
            full_content = msg_obj.get("content", "")
            if not full_content:
                yield {"error": "Empty response from LLM", "messageId": assistant_message_id, "chatId": chat_id}
                return

            yield {"loading-end": {"chatId": chat_id}}

            from django.conf import settings
            chunk_size = settings.STREAMING_CHUNK_SIZE
            chunk_delay = settings.STREAMING_CHUNK_DELAY
            accumulated_content = ""

            for i in range(0, len(full_content), chunk_size):
                if chat_id in ChatService._streaming_control:
                    if not ChatService._streaming_control[chat_id]["should_continue"]:
                        print(f"[SERVICE] Streaming stopped by user for chat_id={chat_id}")
                        streaming_stopped = True
                        full_content = accumulated_content
                        break

                chunk_text = full_content[i : i + chunk_size]
                accumulated_content += chunk_text

                try:
                    yield {
                        "messageId": assistant_message_id,
                        "chatId": chat_id,
                        "role": "assistant",
                        "content": accumulated_content,
                        "v": str(version),
                        "parentId": parent_message.uid if parent_message else None,
                        "currentVersion": None,
                        "totalVersions": None,
                        "resolveMessage": False,
                    }
                    if chunk_delay > 0:
                        import time
                        time.sleep(chunk_delay)
                except GeneratorExit:
                    pass

            if streaming_stopped:
                try:
                    yield {"stop-streaming": {"chatId": chat_id, "messageId": assistant_message_id}}
                except Exception:
                    pass
            else:
                generation_completed = True

        except Exception as e:
            import traceback, logging
            logging.getLogger(__name__).error(
                f"Server Error during generation: {e}, messageId: {assistant_message_id}, chatId: {chat_id}"
            )
            traceback.print_exc()
            try:
                yield {"error": f"Server error: {e}", "messageId": assistant_message_id, "chatId": chat_id}
            except Exception:
                pass

        finally:
            if chat_id in ChatService._streaming_control:
                del ChatService._streaming_control[chat_id]

            if full_content:
                try:
                    assistant_msg = ChatService.add_message(
                        chat_session,
                        "assistant",
                        full_content,
                        parent=parent_message,
                        message_uid=uuid.UUID(assistant_message_id),
                    )
                    if generation_completed:
                        ChatService.increment_usage(user, ip_address)
                except Exception as save_error:
                    import logging
                    logging.getLogger(__name__).error(
                        f"Failed to save assistant message: {save_error}, messageId: {assistant_message_id}"
                    )

            if generation_completed and full_content:
                try:
                    yield {
                        "messageId": assistant_message_id,
                        "chatId": chat_id,
                        "role": "assistant",
                        "content": full_content,
                        "v": str(version),
                        "parentId": parent_message.uid if parent_message else None,
                        "currentVersion": assistant_msg.current_version if assistant_msg else 1,
                        "totalVersions": assistant_msg.total_versions if assistant_msg else 1,
                        "resolveMessage": ChatService.should_show_resolve_message(user),
                    }
                except Exception:
                    pass

