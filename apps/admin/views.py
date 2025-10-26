import os
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import views
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.ChatSessions.models import ChatSession
from apps.messages.models import Message


@staff_member_required
def admin_messages_view(request):
    """
    Admin interface for viewing and managing chat messages
    Protected view that requires staff member authentication
    """
    # Path to the static HTML file
    html_path = os.path.join(settings.BASE_DIR, 'server', 'static', 'index.html')
    
    try:
        with open(html_path, 'r', encoding='utf-8') as file:
            html_content = file.read()
        
        return HttpResponse(html_content, content_type='text/html')
    
    except FileNotFoundError:
        return HttpResponse(
            '<h1>Admin Messages Interface</h1><p>HTML file not found</p>', 
            content_type='text/html',
            status=404
        )


@staff_member_required
def admin_index_redirect(request):
    """
    Redirect to admin messages interface
    Protected view that requires staff member authentication
    """
    return HttpResponse(
        """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Admin Navigation</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 40px; }
                .button { 
                    display: inline-block; 
                    padding: 10px 20px; 
                    margin: 10px; 
                    background: #417690; 
                    color: white; 
                    text-decoration: none; 
                    border-radius: 4px; 
                }
                .button:hover { background: #264b5d; }
            </style>
        </head>
        <body>
            <h1>Admin Navigation</h1>
            <a href="/admin/" class="button">Django Admin Home</a>
            <a href="/admin/llm/messages-interface/" class="button">Messages Interface</a>
        </body>
        </html>
        """,
        content_type='text/html'
    )


class AdminFiltersView(views.APIView):
    """
    API endpoint for getting admin panel sidebar filters
    Dynamically generates URLs from registered Django admin models
    """
    permission_classes = []
    
    @method_decorator(staff_member_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        from django.contrib import admin
        from django.urls import reverse, NoReverseMatch
        import logging
        
        logger = logging.getLogger(__name__)
        
        # Helper function to generate admin URLs dynamically
        def get_admin_url(app_label, model_name, action='changelist'):
            try:
                if action == 'changelist':
                    return reverse(f'admin:{app_label}_{model_name}_changelist')
                elif action == 'add':
                    return reverse(f'admin:{app_label}_{model_name}_add')
            except NoReverseMatch as e:
                # Fallback to manual URL construction if reverse fails
                logger.warning(f"Failed to reverse URL for {app_label}.{model_name} ({action}): {str(e)}")
                if action == 'changelist':
                    return f'/admin/{app_label}/{model_name}/'
                elif action == 'add':
                    return f'/admin/{app_label}/{model_name}/add/'
            return '#'
        
        # Build filters data dynamically from registered models
        filters_data = [
            {
                "sectionTitle": "AUTHENTICATION AND AUTHORIZATION",
                "list": [
                    {
                        "itemTitle": "Groups",
                        "titleLink": get_admin_url('auth', 'group'),
                        "addLink": get_admin_url('auth', 'group', 'add')
                    }
                ]
            },
            {
                "sectionTitle": "CHAT INTEGRATION",
                "list": [
                    {
                        "itemTitle": "Anonymous usage limits",
                        "titleLink": get_admin_url('anonymousUsageLimits', 'anonymoususagelimit'),
                        "addLink": get_admin_url('anonymousUsageLimits', 'anonymoususagelimit', 'add')
                    },
                    {
                        "itemTitle": "Attached files",
                        "titleLink": get_admin_url('attachedFiles', 'attachedfile'),
                        "addLink": get_admin_url('attachedFiles', 'attachedfile', 'add')
                    },
                    {
                        "itemTitle": "Chat sessions",
                        "titleLink": get_admin_url('ChatSessions', 'chatsession'),
                        "addLink": get_admin_url('ChatSessions', 'chatsession', 'add')
                    },
                    {
                        "itemTitle": "Feedbacks",
                        "titleLink": get_admin_url('feedbacks', 'feedback'),
                        "addLink": get_admin_url('feedbacks', 'feedback', 'add')
                    },
                    {
                        "itemTitle": "Messages",
                        "titleLink": get_admin_url('chat_messages', 'message'),
                        "addLink": get_admin_url('chat_messages', 'message', 'add')
                    },
                    {
                        "itemTitle": "Usage limits",
                        "titleLink": get_admin_url('usageLimits', 'usagelimit'),
                        "addLink": get_admin_url('usageLimits', 'usagelimit', 'add')
                    }
                ]
            },
            {
                "sectionTitle": "PAYMENTS",
                "list": [
                    {
                        "itemTitle": "Billing plans",
                        "titleLink": get_admin_url('payments', 'billingplan'),
                        "addLink": get_admin_url('payments', 'billingplan', 'add')
                    },
                    {
                        "itemTitle": "Subscriptions",
                        "titleLink": get_admin_url('payments', 'subscription'),
                        "addLink": get_admin_url('payments', 'subscription', 'add')
                    }
                ]
            },
            {
                "sectionTitle": "PYTHON SOCIAL AUTH",
                "list": [
                    {
                        "itemTitle": "Associations",
                        "titleLink": get_admin_url('social_django', 'association'),
                        "addLink": get_admin_url('social_django', 'association', 'add')
                    },
                    {
                        "itemTitle": "Nonces",
                        "titleLink": get_admin_url('social_django', 'nonce'),
                        "addLink": get_admin_url('social_django', 'nonce', 'add')
                    },
                    {
                        "itemTitle": "User social auths",
                        "titleLink": get_admin_url('social_django', 'usersocialauth'),
                        "addLink": get_admin_url('social_django', 'usersocialauth', 'add')
                    }
                ]
            },
            {
                "sectionTitle": "USERS",
                "list": [
                    {
                        "itemTitle": "Users",
                        "titleLink": get_admin_url('users', 'user'),
                        "addLink": get_admin_url('users', 'user', 'add')
                    }
                ]
            }
        ]
        
        return Response(filters_data)


class AdminChatsView(views.APIView):
    """
    API endpoint for getting chat sessions with pagination for admin panel
    """
    permission_classes = []
    parser_classes = [JSONParser, FormParser, MultiPartParser]
    
    @method_decorator(staff_member_required)
    @method_decorator(csrf_exempt)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        from django.db.models.functions import TruncMonth
        from django.db.models import Count
        from django.core.cache import cache
        from datetime import datetime
        import logging
        
        logger = logging.getLogger(__name__)
        
        page = request.GET.get('page', 1)
        message_search = request.GET.get('message', '').strip()
        email_search = request.GET.get('email', '').strip()
        date_filter = request.GET.get('date', '').strip()
        
        # Validate page number
        try:
            page = int(page)
            if page < 1:
                page = 1
        except (ValueError, TypeError):
            logger.warning(f"Invalid page number received: {request.GET.get('page')}")
            page = 1
        
        # Get all chat sessions with user info, ordered by most recent
        # Using select_related to avoid N+1 queries
        chat_sessions = ChatSession.objects.select_related('user').order_by('-created_at')
        
        # Apply search filters if provided
        if message_search:
            # Using distinct() to avoid duplicates when filtering by related messages
            logger.info(f"Filtering chats by message content: {message_search}")
            chat_sessions = chat_sessions.filter(messages__content__icontains=message_search).distinct()
        
        if email_search:
            logger.info(f"Filtering chats by email: {email_search}")
            chat_sessions = chat_sessions.filter(user__email__icontains=email_search)
        
        # Apply date filter if provided
        date_filter_error = None
        if date_filter and date_filter.lower() != 'all':
            try:
                # Parse date filter like "April+2024" or "April 2024"
                date_str = date_filter.replace('+', ' ')
                filter_date = datetime.strptime(date_str, '%B %Y')
                
                # Filter by year and month using efficient database query
                chat_sessions = chat_sessions.filter(
                    created_at__year=filter_date.year,
                    created_at__month=filter_date.month
                )
                logger.info(f"Applied date filter: {date_str}")
            except ValueError as e:
                # Invalid date format - log warning and continue without filter
                logger.warning(f"Invalid date filter format: {date_filter}, error: {str(e)}")
                date_filter_error = f"Invalid date format: {date_filter}"
        
        # Paginate results (25 items per page)
        paginator = Paginator(chat_sessions, 25)
        page_obj = paginator.get_page(page)
        
        # Format data
        data = []
        for session in page_obj:
            data.append({
                "uid": str(session.id),
                "email": session.user.email if session.user else "Anonymous",
                "session": session.title or "New chat"
            })
        
        # Generate date filters with caching (cache for 5 minutes)
        cache_key = 'admin_chat_date_filters'
        date_filters = None
        
        try:
            date_filters = cache.get(cache_key)
        except Exception as e:
            logger.warning(f"Cache error while getting date filters: {str(e)}")
        
        if date_filters is None:
            logger.info("Generating date filters (cache miss or error)")
            chat_months = (ChatSession.objects
                          .annotate(month=TruncMonth('created_at'))
                          .values('month')
                          .annotate(count=Count('id'))
                          .order_by('-month'))
            
            date_filters = [{
                "name": "All dates",
                "value": "all",
                "active": not date_filter or date_filter.lower() == 'all'
            }]
            
            for month_data in chat_months:
                if month_data['month']:
                    month_name = month_data['month'].strftime('%B %Y')
                    month_value = month_data['month'].strftime('%B+%Y')
                    date_filters.append({
                        "name": f"{month_name} ({month_data['count']})",
                        "value": month_value,
                        "active": False  # Will be set below based on current filter
                    })
            
            # Cache for 5 minutes (300 seconds)
            try:
                cache.set(cache_key, date_filters, 300)
            except Exception as e:
                logger.warning(f"Cache error while setting date filters: {str(e)}")
        
        # Update active state based on current filter
        for filter_item in date_filters:
            filter_item['active'] = (filter_item['value'] == date_filter or 
                                    (filter_item['value'] == 'all' and (not date_filter or date_filter.lower() == 'all')))
        
        response_data = {
            "data": data,
            "dateFilters": date_filters,
            "pagesAmount": paginator.num_pages,
            "activePage": page_obj.number
        }
        
        # Add warning if date filter was invalid
        if date_filter_error:
            response_data['warning'] = date_filter_error
        
        return Response(response_data)


class AdminChatMessagesView(views.APIView):
    """
    API endpoint for getting messages of a specific chat session
    """
    permission_classes = []
    parser_classes = [JSONParser, FormParser, MultiPartParser]
    
    @method_decorator(staff_member_required)
    @method_decorator(csrf_exempt)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        import logging
        
        logger = logging.getLogger(__name__)
        
        chat_id = request.GET.get('chatId')
        
        # Validate required parameter
        if not chat_id:
            logger.warning("Chat messages request without chatId parameter")
            return Response({
                "error": "Missing required parameter",
                "details": "chatId parameter is required",
                "example": "/api/chats/messages/?chatId=123"
            }, status=400)
        
        # Validate chatId format (should be numeric)
        try:
            chat_id_int = int(chat_id)
        except (ValueError, TypeError):
            logger.warning(f"Invalid chatId format: {chat_id}")
            return Response({
                "error": "Invalid parameter format",
                "details": f"chatId must be a valid integer, received: {chat_id}",
                "chatId": chat_id
            }, status=400)
        
        # Get chat session
        try:
            chat_session = ChatSession.objects.select_related('user').get(id=chat_id_int)
            logger.info(f"Fetching messages for chat {chat_id_int} (user: {chat_session.user.email if chat_session.user else 'Anonymous'})")
        except ChatSession.DoesNotExist:
            logger.warning(f"Chat session not found: {chat_id_int}")
            return Response({
                "error": "Chat session not found",
                "details": f"No chat session exists with id: {chat_id_int}",
                "chatId": chat_id_int
            }, status=404)
        
        # Get total message count first (before slicing)
        MAX_MESSAGES = 1000
        total_messages = Message.objects.filter(chat_session=chat_session).count()
        
        # Log if hit the limit
        if total_messages > MAX_MESSAGES:
            logger.warning(f"Chat {chat_id_int} has {total_messages} messages, limiting to {MAX_MESSAGES}")
        
        # Get messages with limit to prevent huge responses
        messages = Message.objects.filter(chat_session=chat_session).order_by('created_at')[:MAX_MESSAGES]
        
        # JS ожидает просто массив сообщений с role и content
        data = []
        for message in messages:
            data.append({
                "role": message.role,
                "content": message.content
            })
        
        logger.info(f"Returning {len(data)} messages for chat {chat_id_int}")
        return Response(data)


class AdminBreadcrumbsView(views.APIView):
    """
    API endpoint for getting breadcrumbs navigation for admin panel
    """
    permission_classes = []
    
    @method_decorator(staff_member_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        # Static breadcrumbs data for admin messages interface
        breadcrumbs = [
            { "text": "Home", "link": "/admin/" },
            { "text": "Chat Integration", "link": "/admin/llm/" },
            { "text": "Messages", "link": "/admin/llm/messages-interface/" }
        ]
        
        return Response(breadcrumbs)


class AdminDateFiltersView(views.APIView):
    """
    API endpoint for getting date filters for admin panel
    """
    permission_classes = []
    
    @method_decorator(staff_member_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        from django.db.models.functions import TruncMonth
        from django.db.models import Count
        
        # Get chat sessions grouped by month with counts
        chat_months = (ChatSession.objects
                      .annotate(month=TruncMonth('created_at'))
                      .values('month')
                      .annotate(count=Count('id'))
                      .order_by('-month'))
        
        date_filters = [{"label": "All", "value": "all"}]
        
        for month_data in chat_months:
            if month_data['month']:
                month_name = month_data['month'].strftime('%B %Y')
                date_filters.append({
                    "label": f"{month_name} ({month_data['count']})",
                    "value": month_name.replace(' ', '+')
                })
        
        return Response(date_filters)