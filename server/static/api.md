# API Документация

Документация для всех API endpoints, используемых в Django Admin Panel.

## 1. GET /api/filters/

**Описание:** Возвращает структурированные данные для отображения левой навигационной панели с разделами и ссылками.

**Query параметры:** нет

**Schema ответа:**

```typescript
Array<{
  sectionTitle: string
  list: Array<{
    itemTitle: string
    titleLink: string
    addLink: string
  }>
}>
```

**Response:**

```json
[
  {
    "sectionTitle": "Authentication and Authorization",
    "list": [
      {
        "itemTitle": "Groups",
        "titleLink": "/admin/auth/groups/",
        "addLink": "/admin/auth/groups/add/"
      },
      {
        "itemTitle": "Users",
        "titleLink": "/admin/auth/users/",
        "addLink": "/admin/auth/users/add/"
      }
    ]
  },
  {
    "sectionTitle": "LLM Integration",
    "list": [
      {
        "itemTitle": "Messages",
        "titleLink": "/admin/llm/messages/",
        "addLink": "/admin/llm/messages/add/"
      }
    ]
  }
]
```

## 2. GET /api/chats/

**Описание:** Основной endpoint для получения списка чатов с пагинацией, поиском и фильтрами. Возвращает данные чатов, информацию о пагинации и актуальные фильтры по датам в одном запросе.

**Query параметры:**

- `page` (int, optional) - номер страницы для пагинации (по умолчанию 1)
- `message` (string, optional) - поиск по содержимому сообщений в чатах
- `email` (string, optional) - поиск по email пользователей
- `date` (string, optional) - фильтрация по дате (значение из фильтров дат)

**Примеры запросов:**

- `GET /api/chats/?page=1`
- `GET /api/chats/?page=1&message=hello`
- `GET /api/chats/?page=1&email=admin@test.com`
- `GET /api/chats/?page=1&date=april_2024`
- `GET /api/chats/?page=1&message=hello&email=user@example.com&date=april_2024`

**Schema ответа:**

```typescript
{
  pagesAmount: number,
  activePage: number,
  data: Array<{
    uid: string,
    email: string,
    session: string
  }>,
  dateFilters: Array<{
    name: string,
    value: string,
    active: boolean
  }>
}
```

**Response:**

```json
{
  "pagesAmount": 29,
  "activePage": 1,
  "data": [
    {
      "uid": "c7d229bd-26c4-4757-9edb-cbe5f7765ca4",
      "email": "da000shi@gmail.com",
      "session": "New chat"
    },
    {
      "uid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "email": "user@example.com",
      "session": "Previous chat"
    }
  ],
  "dateFilters": [
    {
      "name": "All dates",
      "value": "all",
      "active": false
    },
    {
      "name": "April 2024",
      "value": "april_2024",
      "active": true
    }
  ]
}
```

**Поля ответа:**

- `pagesAmount` (int) - общее количество страниц
- `activePage` (int) - текущая активная страница
- `data` (array) - массив объектов чатов
- `dateFilters` (array) - доступные фильтры по датам с флагом активности

**Логика работы фильтров по датам:**

Поле `dateFilters` содержит массив всех доступных фильтров с их состоянием:

- `name` (string) - отображаемое название фильтра (например, "April 2024", "All dates")
- `value` (string) - значение фильтра, которое передается в параметре `date` при запросе
- `active` (boolean) - флаг активности фильтра:
  - `true` - этот фильтр сейчас применен (должен быть подсвечен в UI)
  - `false` - фильтр доступен, но не активен

**Правила установки `active`:**

- Если передан параметр `date=april_2024`, то `active: true` у фильтра с `value: "april_2024"`
- Если параметр `date` не передан или `date=all`, то `active: true` у фильтра "All dates"
- У всех остальных фильтров должно быть `active: false`
- Одновременно может быть активен только один фильтр

## 3. GET /api/chats/messages/

**Описание:** Возвращает список сообщений для конкретного чата.

**Query параметры:**

- `chatId` (string, required) - UUID чата для получения сообщений

**Schema ответа:**

```typescript
Array<{
  role: "user" | "assistant"
  content: string
}>
```

**Response:**

```json
[
  {
    "role": "user",
    "content": "Здравствуйте!"
  },
  {
    "role": "assistant",
    "content": "Добрый день! Как дела?"
  }
]
```

## 4. GET /api/breadcrumbs/

**Описание:** Возвращает массив элементов для отображения навигационных хлебных крошек в верхней части страницы.

**Query параметры:** нет

**Schema ответа:**

```typescript
Array<{
  text: string
  link: string
}>
```

**Response:**

```json
[
  { "text": "Home", "link": "/" },
  { "text": "LLM Integration", "link": "/admin/llm/" },
  { "text": "Messages", "link": "/admin/llm/messages/" }
]
```

## 5. DELETE /api/chats/

**Описание:** Удаляет несколько чатов по их ID. Принимает массив UUID чатов для удаления.

**Query параметры:** нет

**Body параметры:**

**Schema body:**

```typescript
string[]
```

```json
["c7d229bd-26c4-4757-9edb-cbe5f7765ca4", "a1b2c3d4-e5f6-7890-abcd-ef1234567890"]
```

**Response:**

- `200` - успешное удаление
- `400` - некорректные данные в запросе
- `404` - один или несколько чатов не найдены
- `500` - внутренняя ошибка сервера
