# SentX AI Chat Server

SentX is a generative artificial intelligence chatbot backend built with Django and Django REST Framework.

## Features

- 🤖 **AI Chat API** - RESTful API for chat interactions with AI
- 🔐 **Authentication** - JWT-based authentication with social auth (Google, Twitter)
- 💳 **Payments** - Stripe integration for subscriptions and billing
- 📊 **Usage Limits** - Request limits for authenticated and anonymous users
- 🎯 **Admin Panel** - Custom Django admin interface with chat management
- 🌊 **SSE Streaming** - Server-Sent Events for real-time AI responses
- 🌳 **Message Branching** - Edit messages and regenerate responses with full branch history (like ChatGPT)
- 📁 **File Attachments** - Support for file uploads in chat messages
- 👍 **Feedback System** - User feedback on AI responses

## Architecture

The project uses a modular architecture where each model has its own Django application:

```
sentx-new-server/
├── server/              # Main Django project
├── apps/                # Django applications
│   ├── users/          # User management
│   ├── payments/       # Stripe payments
│   ├── ChatSessions/   # Chat sessions
│   ├── messages/       # Chat messages
│   ├── feedbacks/      # Message feedback
│   ├── attachedFiles/  # File attachments
│   ├── usageLimits/    # Usage limits
│   ├── anonymousUsageLimits/  # Anonymous user limits
│   ├── chat/           # Chat API endpoints
│   └── admin/          # Custom admin interface
├── service/            # Business logic (non-Django)
│   └── llm/           # LLM provider abstraction
└── documentation/      # API documentation
```

## Requirements

- Python 3.12+
- PostgreSQL (production) or SQLite (development)
- Redis (optional, for caching)

## Installation

### 1. Clone the repository

```bash
git clone <repository-url>
cd sentx-new-server
```

### 2. Create virtual environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -e .
```

### 4. Create `.env` file

Copy the example environment file and configure it:

```bash
cp env.example .env
```

Edit `.env` with your settings (see Configuration section below).

### 5. Run migrations

```bash
python manage.py migrate
```

### 6. Create superuser

```bash
python manage.py createsuperuser
```

### 7. Collect static files

```bash
python manage.py collectstatic --noinput
```

### 8. Run development server

```bash
python manage.py runserver
```

The server will be available at `http://localhost:8000`

## Configuration

### Environment Variables

Create a `.env` file in the root directory with the following variables:

```env
# Django
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/sentx_db

# SentX API (LLM)
SENTX_SECRET_KEY=your-sentx-api-key
OPENAI_BASE_URL=https://api.sentx.ai/v1
OPENAI_DEFAULT_MODEL=sentx_4.0

# Alternative OpenAI API (if not using SentX)
OPENAI_API_KEY=your-openai-api-key

# Stripe
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_API_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Google OAuth2
GOOGLE_OAUTH2_KEY=your-google-client-id
GOOGLE_OAUTH2_SECRET=your-google-client-secret

# Twitter OAuth2
TWITTER_OAUTH2_KEY=your-twitter-client-id
TWITTER_OAUTH2_SECRET=your-twitter-client-secret

# Social Auth URLs
SOCIAL_AUTH_LOGIN_REDIRECT_URL=http://localhost:5173/auth/google/callback
SOCIAL_AUTH_LOGIN_ERROR_URL=http://localhost:5173/auth/error

# Email (Yandex SMTP)
EMAIL_HOST_USER=your-email@example.com
EMAIL_HOST_PASSWORD=your-password

# Security
ABFUSCATOR_ID_KEY=your-secret-abfuscator-key
```

## API Endpoints

### Authentication

- `POST /api/token/` - Obtain JWT token
- `POST /api/token/refresh/` - Refresh JWT token
- `POST /api/auth/users/` - Register user (Djoser)
- `GET /api/auth/users/me/` - Get current user
- `GET /api/auth/users/social/<provider>/` - Social auth callback

### Chat

- `POST /chat/messages` - Send message to chat
- `GET /chat/stream?chatId=<id>` - SSE stream for AI responses
- `GET /chat/history?chatId=<id>` - Get chat history
- `GET /chat/sessions/` - List user's chat sessions
- `POST /chat/sessions/` - Create new chat session
- `GET /chat/sessions/<id>/` - Get chat session
- `PATCH /chat/sessions/<id>/` - Update chat session
- `DELETE /chat/sessions/<id>/` - Delete chat session
- `POST /chat/switch-branch/` - Switch active branch (message branching)
- `POST /api/regeneration/` - Regenerate assistant response (creates new branch)

### Payments

- `GET /api/payments/billing-plans/` - List billing plans
- `POST /api/payments/subscriptions/` - Create subscription
- `GET /api/payments/subscriptions/` - List user subscriptions
- `POST /api/payments/webhook/` - Stripe webhook

### Usage Limits

- `GET /api/usage-limits/` - Get usage limits for current user

### API Documentation

- `GET /api/swagger/` - Swagger UI
- `GET /api/redoc/` - ReDoc UI
- `GET /api/schema/` - OpenAPI schema

## Message Branching

Система ветвления диалогов позволяет редактировать сообщения и регенерировать ответы, сохраняя все ветки истории. Сообщения организованы в дерево с `parent`/`active_child` указателями.

**Ключевые изменения:**

- **Message** — новые поля: `parent`, `active_child`, `current_version`, `total_versions`
- **ChatSession** — новое поле: `current_node` (текущий лист активной ветки)
- **ChatService** — новые методы: `get_active_branch()`, `get_active_branch_for_llm()`, `switch_branch()`, `get_siblings_info()`
- **Регенерация** — создаёт новый sibling вместо перезаписи, сохраняя старую ветку
- **API** — все ответы и SSE-события содержат `parentId`, `currentVersion`, `totalVersions`
- **Новый эндпоинт** — `POST /api/chat/switch-branch/` для переключения между ветками

Подробная документация: [`docs/message-branching.md`](docs/message-branching.md)

## Development

### Run tests

```bash
pytest
```

### Code formatting

```bash
black .
```

### Linting

```bash
ruff check .
```

### Type checking

```bash
mypy .
```

## Deployment

### Using Docker

```bash
docker-compose up -d
```

### Manual deployment

1. Set `DEBUG=False` in `.env`
2. Configure production database (PostgreSQL)
3. Set proper `ALLOWED_HOSTS`
4. Configure HTTPS and SSL certificates
5. Use gunicorn as WSGI server:

```bash
gunicorn server.wsgi:application --bind 0.0.0.0:8000
```

6. Configure Nginx as reverse proxy
7. Set up SSL with Let's Encrypt

## Admin Panel

Access the admin panel at `/admin/`

Custom admin interface for chat management: `/admin/llm/messages-interface/`

## License

Proprietary - All rights reserved

## Support

For support, contact: develop@kuki.agency

