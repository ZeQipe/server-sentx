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


def admin_index_redirect(request):
    """
    Redirect to admin messages interface
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
    """
    permission_classes = []
    
    @method_decorator(staff_member_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        # Static filters data for admin panel sidebar - all models from Django admin
        filters_data = [
            {
                "sectionTitle": "AUTHENTICATION AND AUTHORIZATION",
                "list": [
                    {
                        "itemTitle": "Groups",
                        "titleLink": "/admin/auth/group/",
                        "addLink": "/admin/auth/group/add/"
                    }
                ]
            },
            {
                "sectionTitle": "CHAT INTEGRATION",
                "list": [
                    {
                        "itemTitle": "Anonymous usage limits",
                        "titleLink": "/admin/anonymoususagelimits/anonymoususagelimit/",
                        "addLink": "/admin/anonymoususagelimits/anonymoususagelimit/add/"
                    },
                    {
                        "itemTitle": "Attached files",
                        "titleLink": "/admin/attachedfiles/attachedfile/",
                        "addLink": "/admin/attachedfiles/attachedfile/add/"
                    },
                    {
                        "itemTitle": "Chat sessions",
                        "titleLink": "/admin/chatsessions/chatsession/",
                        "addLink": "/admin/chatsessions/chatsession/add/"
                    },
                    {
                        "itemTitle": "Feedbacks",
                        "titleLink": "/admin/feedbacks/feedback/",
                        "addLink": "/admin/feedbacks/feedback/add/"
                    },
                    {
                        "itemTitle": "Messages",
                        "titleLink": "/admin/messages/message/",
                        "addLink": "/admin/messages/message/add/"
                    },
                    {
                        "itemTitle": "Usage limits",
                        "titleLink": "/admin/usagelimits/usagelimit/",
                        "addLink": "/admin/usagelimits/usagelimit/add/"
                    }
                ]
            },
            {
                "sectionTitle": "PAYMENTS",
                "list": [
                    {
                        "itemTitle": "Billing plans",
                        "titleLink": "/admin/payments/billingplan/",
                        "addLink": "/admin/payments/billingplan/add/"
                    },
                    {
                        "itemTitle": "Subscriptions",
                        "titleLink": "/admin/payments/subscription/",
                        "addLink": "/admin/payments/subscription/add/"
                    }
                ]
            },
            {
                "sectionTitle": "PYTHON SOCIAL AUTH",
                "list": [
                    {
                        "itemTitle": "Associations",
                        "titleLink": "/admin/social_django/association/",
                        "addLink": "/admin/social_django/association/add/"
                    },
                    {
                        "itemTitle": "Nonces",
                        "titleLink": "/admin/social_django/nonce/",
                        "addLink": "/admin/social_django/nonce/add/"
                    },
                    {
                        "itemTitle": "User social auths",
                        "titleLink": "/admin/social_django/usersocialauth/",
                        "addLink": "/admin/social_django/usersocialauth/add/"
                    }
                ]
            },
            {
                "sectionTitle": "USERS",
                "list": [
                    {
                        "itemTitle": "Users",
                        "titleLink": "/admin/users/user/",
                        "addLink": "/admin/users/user/add/"
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
        page = request.GET.get('page', 1)
        message_search = request.GET.get('message', '').strip()
        email_search = request.GET.get('email', '').strip()
        date_filter = request.GET.get('date', '').strip()
        
        try:
            page = int(page)
        except (ValueError, TypeError):
            page = 1
        
        # Get all chat sessions with user info, ordered by most recent
        chat_sessions = ChatSession.objects.select_related('user').order_by('-created_at')
        
        # Apply search filters if provided
        if message_search:
            chat_sessions = chat_sessions.filter(messages__content__icontains=message_search).distinct()
        
        if email_search:
            chat_sessions = chat_sessions.filter(user__email__icontains=email_search)
        
        # Apply date filter if provided
        if date_filter and date_filter.lower() != 'all':
            try:
                from datetime import datetime
                # Parse date filter like "April+2024" or "April 2024"
                date_str = date_filter.replace('+', ' ')
                filter_date = datetime.strptime(date_str, '%B %Y')
                
                # Filter by year and month using efficient database query
                chat_sessions = chat_sessions.filter(
                    created_at__year=filter_date.year,
                    created_at__month=filter_date.month
                )
            except ValueError:
                # Invalid date format, ignore filter silently
                pass
        
        # Paginate results (25 items per page)
        paginator = Paginator(chat_sessions, 25)
        page_obj = paginator.get_page(page)
        
        # Format data
        data = []
        for session in page_obj:
            data.append({
                "uid": str(session.id),  # Use regular ID for now
                "email": session.user.email if session.user else "Anonymous",
                "session": session.title or "New chat"
            })
        
        return Response({
            "data": data,
            "pagination": {
                "current_page": page_obj.number,
                "total_pages": paginator.num_pages,
                "has_next": page_obj.has_next(),
                "has_previous": page_obj.has_previous(),
            }
        })


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
        chat_id = request.GET.get('chatId')
        if not chat_id:
            return Response({"error": "chatId parameter is required"}, status=400)
        
        try:
            chat_session = ChatSession.objects.get(id=chat_id)
        except ChatSession.DoesNotExist:
            return Response({"error": "Chat session not found"}, status=404)
        
        messages = Message.objects.filter(chat_session=chat_session).order_by('created_at')
        
        data = []
        for message in messages:
            data.append({
                "uid": message.uid,
                "role": message.role,
                "content": message.content,
                "created_at": message.created_at.isoformat()
            })
        
        return Response({
            "data": data,
            "chat_session": {
                "id": chat_session.id,
                "title": chat_session.title,
                "user": chat_session.user.email if chat_session.user else "Anonymous"
            }
        })


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