# Класс PageRenderer

## Описание

Класс `PageRenderer` отвечает за рендеринг всех элементов интерфейса Django Admin Panel: боковой панели, таблицы чатов, пагинации и окон чатов.

## Конструктор

```javascript
constructor() {
  this.root = document
  this.leftContainer = this.root.querySelector(".js-left-list")
  this.centerContainer = this.root.querySelector(".js-messages-list")
  this.paginationContainer = this.root.querySelector(".js-pagination")
  this.selectAllCheckbox = this.root.querySelector(".table__checkbox--select-all")
  this.openChatRow = null                    // Ссылка на открытую строку чата
  this.currentChatMessages = null            // Текущие сообщения чата
  this.selectionElement = this.root.querySelector(".main__selection")
  this.totalItemsOnPage = 0                  // Количество элементов на странице
}
```

## Публичные методы

### renderLeftColumn(sections)

**Описание:** Рендерит левую боковую панель (sidebar) с секциями и элементами меню.

**Параметры:**

- `sections` (Array) - массив объектов секций

**Формат данных:**

```javascript
;[
  {
    sectionTitle: "Authentication and Authorization", // заголовок секции
    list: [
      {
        itemTitle: "Groups", // название элемента
        titleLink: "/admin/groups", // ссылка на элемент
        addLink: "/admin/groups/add", // ссылка на добавление
      },
    ],
  },
]
```

**Возвращает:** void

---

### renderChatsList(items)

**Описание:** Рендерит основную таблицу с чатами, включая чекбоксы, UID, сессии и email.

**Параметры:**

- `items` (Array) - массив объектов чатов

**Формат данных:**

```javascript
;[
  {
    uid: "c7d229bd-26c4-4757-9edb-cbe5f7765ca4", // ID чата
    email: "user@example.com", // email пользователя
    session: "New chat", // название сессии
  },
]
```

**Побочные эффекты:**

- Обновляет счетчик выбранных элементов
- Сбрасывает чекбокс "выбрать все"
- Настраивает обработчики событий для чекбоксов

**Возвращает:** void

---

### renderPagination({ pagesAmount, activePage })

**Описание:** Рендерит пагинацию внизу таблицы.

**Параметры:**

- `pagesAmount` (number) - общее количество страниц
- `activePage` (number) - номер активной страницы

**Возвращает:** void

---

### chatMessageRender(chatId, messages)

**Описание:** Открывает чат для конкретного ID и отображает переданные сообщения.

**Параметры:**

- `chatId` (string) - ID чата (ищется по textContent кнопки UID)
- `messages` (Array) - массив сообщений

**Формат сообщений:**

```javascript
;[
  { role: "user", content: "Привет!" },
  { role: "assistant", content: "Здравствуйте!" },
]
```

**Особенности:**

- Ищет чат по `textContent` кнопки UID, а не по `data-chatid`
- Если чат не найден, метод завершается без ошибки

**Возвращает:** void

---

### setMessageContent(messages)

**Описание:** Сохраняет сообщения глобально для текущего чата.

**Параметры:**

- `messages` (Array) - массив сообщений

**Формат сообщений:**

```javascript
;[
  { role: "user", content: "Текст сообщения" },
  { role: "assistant", content: "Ответ ассистента" },
]
```

**Побочные эффекты:**

- Сохраняет сообщения в `this.currentChatMessages`
- Нормализует сообщения через `#normalizeMessages`

**Возвращает:** void

---

### openChatById(chatId, messages)

**Описание:** Находит чат по ID и открывает его с переданными сообщениями.

**Параметры:**

- `chatId` (string) - ID чата (ищется по data-chatid атрибуту)
- `messages` (Array) - массив сообщений для отображения

**Формат сообщений:**

```javascript
;[
  { role: "user", content: "Сообщение пользователя" },
  { role: "assistant", content: "Ответ ассистента" },
]
```

**Особенности:**

- Ищет чат по `data-chatid` атрибуту кнопки
- Если чат не найден, выводит предупреждение в консоль
- Автоматически сохраняет сообщения и открывает чат
- Закрывает предыдущий открытый чат

**Возвращает:** void

---

## Различия между методами открытия чата

| Метод                                 | Поиск чата                  | Использование           |
| ------------------------------------- | --------------------------- | ----------------------- |
| `chatMessageRender(chatId, messages)` | По `textContent` кнопки UID | Устаревший метод        |
| `openChatById(chatId, messages)`      | По `data-chatid` атрибуту   | **Рекомендуемый метод** |

## Приватные методы

### #openChatForRow(row, item, messages)

Открывает окно чата под указанной строкой таблицы.

### #closeChatForRow(row)

Закрывает окно чата для указанной строки.

### #normalizeMessages(messages)

Нормализует массив сообщений, приводя к стандартному формату.

### #setupSelectAll()

Настраивает обработчик для чекбокса "выбрать все".

### #setupRowCheckboxListeners()

Настраивает обработчики для чекбоксов строк.

### #updateSelectionText()

Обновляет текст счетчика выбранных элементов.

### #generatePageNumbers(total, current)

Генерирует массив номеров страниц для пагинации.

### #safeText(value, fallback)

Безопасно извлекает текст из значения с fallback.

## Логика работы с чатами

1. **Открытие чата:**

   - Пользователь кликает по UID чата
   - Глобальный обработчик ловит клик
   - Вызывается `fetchChatMessages(chatId)`
   - После загрузки вызывается `openChatById(chatId, messages)`

2. **Управление состоянием:**

   - `this.openChatRow` - хранит ссылку на открытую строку
   - `this.currentChatMessages` - хранит текущие сообщения
   - Только один чат может быть открыт одновременно

3. **Toggle поведение:**
   - Клик по уже открытому чату закрывает его
   - Клик по другому чату закрывает предыдущий и открывает новый

## Интеграция с EventEmitter

Класс работает с глобальным `dataEmitter` для:

- Получения данных для рендеринга
- Уведомления о необходимости загрузки сообщений чата

## Примеры использования

```javascript
// Создание экземпляра
const renderer = new PageRenderer()

// Рендер списка чатов
renderer.renderChatsList([
  { uid: "123", email: "user@test.com", session: "Chat 1" },
])

// Открытие чата с сообщениями
renderer.openChatById("123", [
  { role: "user", content: "Привет!" },
  { role: "assistant", content: "Здравствуйте!" },
])

// Рендер пагинации
renderer.renderPagination({ pagesAmount: 10, activePage: 1 })
```
