# Ветвление диалогов (Message Branching)

## Обзор

Система ветвления диалогов позволяет пользователям редактировать ранее отправленные сообщения и регенерировать ответы ассистента, при этом сохраняя полную историю всех веток. Реализация аналогична ChatGPT.

Сообщения организованы в дерево. Каждое сообщение хранит указатель на родителя (`parent`) и на «активного потомка» (`active_child`). Сессия чата хранит указатель на текущий лист дерева (`current_node`), определяющий отображаемую ветку.

```
null (root)
├── K1 (user)                    ← current_version=1, total_versions=2
│   ├── A1 (assistant)           ← current_version=1, total_versions=2
│   │   └── K2 (user)
│   │       └── A2 (assistant)
│   └── A1' (assistant, regen)   ← current_version=2, total_versions=2
│       └── K3 (user)
│           └── A3 (assistant)   ← current_node (если эта ветка активна)
└── K1' (user, edited)           ← current_version=2, total_versions=2
    └── A1'' (assistant)
```

---

## Изменения в моделях

### Message (apps/messages/models.py)

Добавлены 4 новых поля:

| Поле | Тип | Описание |
|------|-----|----------|
| `parent` | `ForeignKey("self", null=True, SET_NULL)` | Указатель на родительское сообщение. `null` для первого сообщения в чате. `related_name="children"` |
| `active_child` | `ForeignKey("self", null=True, SET_NULL)` | Какого потомка показывать при обходе дерева вниз. `null` для листовых сообщений. `related_name="+"` |
| `current_version` | `IntegerField(default=1)` | Порядковый номер этого сообщения среди siblings (1-based). Позволяет мгновенно отдать «2» из «< 2/3 >» |
| `total_versions` | `IntegerField(default=1)` | Общее количество siblings. Позволяет мгновенно отдать «3» из «< 2/3 >». Обновляется у ВСЕХ siblings при создании нового |

Существующее поле `version` сохранено для обратной совместимости.

### ChatSession (apps/ChatSessions/models.py)

Добавлено 1 новое поле:

| Поле | Тип | Описание |
|------|-----|----------|
| `current_node` | `ForeignKey("messages.Message", null=True, SET_NULL)` | Текущий лист активной ветки. Используется для загрузки истории и определения контекста |

---

## Миграции

### 0002_message_branching (apps/messages/migrations/)

Schema-миграция: добавляет поля `version`, `parent`, `active_child`, `current_version`, `total_versions` в модель `Message`.

### 0004_chatsession_current_node (apps/ChatSessions/migrations/)

Schema-миграция: добавляет поле `current_node` в модель `ChatSession`.

### 0003_populate_branching_data (apps/messages/migrations/)

Data-миграция: для каждой существующей `ChatSession` прошивает линейную цепочку:
- `messages[i].parent = messages[i-1]`
- `messages[i-1].active_child = messages[i]`
- Все `current_version = 1`, `total_versions = 1`
- `chat_session.current_node = messages[-1]`

Обратимая (reverse: обнуляет все новые поля).

---

## Изменения в ChatService (apps/chat/services.py)

### Изменённые методы

#### `add_message(chat_session, role, content, parent=None, message_uid=None, version=1)`

Добавлен параметр `parent`. Логика:
1. Считает количество siblings: `Message.objects.filter(parent=parent, chat_session=..., role=role).count()`
2. Создаёт Message с `current_version = count + 1`, `total_versions = count + 1`
3. Если `count > 0` — обновляет `total_versions` у всех siblings
4. Обновляет `parent.active_child = new_message`
5. Обновляет `chat_session.current_node = new_message`

#### `process_chat_stream(..., parent_message=None)`

Добавлен параметр `parent_message`. Если передан — строит контекст LLM из ветки через `get_active_branch_for_llm(parent_message)` вместо `ORDER BY created_at`. Все SSE-чанки включают `parentId`, `currentVersion`, `totalVersions`.

### Новые методы

#### `get_active_branch(chat_session) -> list[Message]`

Обходит дерево от `chat_session.current_node` вверх по `parent` до корня, возвращает в хронологическом порядке. `current_version` и `total_versions` уже на каждом сообщении — доп. запросы не нужны.

#### `get_active_branch_for_llm(parent_message) -> list[dict]`

Аналогично `get_active_branch`, но от указанного сообщения. Возвращает `[{"role": ..., "content": ...}]` для передачи в LLM.

#### `switch_branch(chat_session, target_message_uid) -> list[Message]`

1. Находит целевое сообщение
2. Обновляет `target.parent.active_child = target`
3. Идёт вниз по `active_child` до листа
4. Обновляет `chat_session.current_node = лист`
5. Возвращает активную ветку

#### `get_siblings_info(message) -> dict`

Возвращает `{ "currentVersion", "totalVersions", "siblings": [uid1, uid2, ...] }`.

---

## Изменения в Serializers (apps/chat/serializers.py)

### Изменённые сериализаторы

| Сериализатор | Новые поля |
|---|---|
| `SendMessageRequestSerializer` | `parentId` (CharField, optional, nullable) |
| `SendMessageResponseSerializer` | `parentId`, `currentVersion`, `totalVersions` |
| `ChatMessageSerializer` | `parentId`, `currentVersion`, `totalVersions` |
| `SSEMessageSerializer` | `parentId`, `currentVersion`, `totalVersions` |

### Новые сериализаторы

| Сериализатор | Поля | Назначение |
|---|---|---|
| `SwitchBranchRequestSerializer` | `chatId` (ObfuscatedIDField), `messageId` (CharField) | POST /api/chat/switch-branch/ |
| `RegenerationRequestSerializer` | `messageId`, `sessionId`, `parentId`, `chatId` | POST /api/regeneration/ |

---

## Изменения в Views (apps/chat/views.py)

### `ChatMessagesView.post()` — POST /api/chat/messages/

**Входящее (новое поле):** `parentId` — uid родительского сообщения.

**Логика:**
- Если `parentId` передан — находит сообщение по uid, использует как parent
- Если `parentId` не передан и чат существует — `parent = chat_session.current_node`
- Для нового чата — `parent = None`
- Передаёт `user_message` как `parent_message` в `process_chat_stream`

**Ответ (новые поля):** `parentId`, `currentVersion`, `totalVersions`

**SSE user message (новые поля):** `parentId`, `currentVersion`, `totalVersions`

### `ChatHistoryView.get()` — GET /api/chat/history?chatId=X

Заменено `get_chat_history()` → `get_active_branch()`. Каждое сообщение в ответе содержит `parentId`, `currentVersion`, `totalVersions`.

### `RegenerationView.post()` — POST /api/regeneration/

**Полная переработка.** Теперь принимает `messageId`, `sessionId`, `parentId`, `chatId` через `RegenerationRequestSerializer`.

Критические изменения:
- **Убрано** удаление последующих сообщений
- **Убрана** перезапись целевого сообщения
- Вместо этого создаётся **новое** assistant-сообщение как sibling через `ChatService.add_message(..., parent=parent_msg)`
- Контекст LLM из `get_active_branch_for_llm(parent_msg)`
- Все SSE-чанки содержат `parentId`, `currentVersion`, `totalVersions`

### `SwitchBranchView` — POST /api/chat/switch-branch/ (новый)

**Request:** `chatId` (obfuscated), `messageId` (uid sibling-сообщения)

**Response:** `chatId` + массив `messages` новой активной ветки (формат как в history)

**Логика:**
1. Деобфусцирует chatId, проверяет ownership
2. Вызывает `ChatService.switch_branch(chat_session, messageId)`
3. Возвращает полную активную ветку

---

## Изменения в PersistentChatMessagesView (apps/chat/persistent_views.py)

Аналогичные изменения:
- Принимает `parentId` в request body
- Резолвит parent message через `_resolve_parent()` helper
- Передаёт `parent` в `ChatService.add_message()`
- Передаёт `user_message` как `parent_message` в `process_chat_stream()`
- SSE user message и HTTP-ответ содержат `parentId`, `currentVersion`, `totalVersions`

---

## Изменения в viewset_serializers.py

### `MessageSerializer`

Добавлены поля:
- `parentId` — `SerializerMethodField()` → `obj.parent.uid if obj.parent_id else None`
- `currentVersion` — `IntegerField(source="current_version")`
- `totalVersions` — `IntegerField(source="total_versions")`

### `ChatSessionSerializer`

Поле `messages` теперь `SerializerMethodField`. Метод `get_messages()` вызывает `ChatService.get_active_branch(instance)` и сериализует результат через `MessageSerializer`. Это гарантирует, что `GET /api/chat/sessions/{id}/` возвращает только сообщения активной ветки.

---

## Изменения в URLs (apps/chat/urls.py)

Добавлен роут:
```
path("switch-branch/", SwitchBranchView.as_view(), name="chat-switch-branch")
```

Полный путь: `POST /api/chat/switch-branch/`

---

## SSE-события — общие правила

Во **всех** SSE-событиях, содержащих данные сообщения, присутствуют три дополнительных поля:

```json
{
  "parentId": "uid родителя или null",
  "currentVersion": 1,
  "totalVersions": 2
}
```

Затрагиваемые места:
- `ChatMessagesView.post()` — user_msg_data, все assistant chunks
- `RegenerationView.post()` — все chunks регенерации
- `ChatService.process_chat_stream()` — все yield chunks
- `PersistentChatMessagesView.post()` — user message SSE

---

## API Reference

### POST /api/chat/messages/

```
Request:  { content, chatId?, parentId? }
Response: { messageId, chatId, isTemporary, parentId, currentVersion, totalVersions }
```

### GET /api/chat/history?chatId=X

```
Response: { chatId, messages: [{ messageId, chatId, role, content, v, createdAt, parentId, currentVersion, totalVersions }] }
```

### GET /api/chat/sessions/{id}/

```
Response: { id, title, created_at, updated_at, messages: [{ id, uid, role, content, version, created_at, parentId, currentVersion, totalVersions }] }
```

### POST /api/regeneration/

```
Request:  { messageId, sessionId, parentId, chatId }
Response: { success, message, messageId, parentId, currentVersion, totalVersions }
```

### POST /api/chat/switch-branch/

```
Request:  { chatId, messageId }
Response: { chatId, messages: [{ messageId, chatId, role, content, v, createdAt, parentId, currentVersion, totalVersions }] }
```

---

## Сводка затронутых файлов

| Файл | Изменения |
|------|-----------|
| `apps/messages/models.py` | +4 поля (parent, active_child, current_version, total_versions) |
| `apps/ChatSessions/models.py` | +1 поле (current_node) |
| `apps/messages/migrations/0002_message_branching.py` | Новый файл — schema migration |
| `apps/messages/migrations/0003_populate_branching_data.py` | Новый файл — data migration |
| `apps/ChatSessions/migrations/0004_chatsession_current_node.py` | Новый файл — schema migration |
| `apps/chat/services.py` | Переработка add_message, process_chat_stream; +4 новых метода |
| `apps/chat/serializers.py` | Расширение 4 сериализаторов, +2 новых |
| `apps/chat/viewset_serializers.py` | Обновление MessageSerializer, ChatSessionSerializer |
| `apps/chat/views.py` | Переработка 3 views; +1 SwitchBranchView |
| `apps/chat/persistent_views.py` | Переработка PersistentChatMessagesView |
| `apps/chat/urls.py` | +1 роут switch-branch/ |
