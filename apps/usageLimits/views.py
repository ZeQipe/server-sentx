from rest_framework import views
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.anonymousUsageLimits.serializers import AnonymousUsageLimitSerializer
from apps.anonymousUsageLimits.service import AnonymousUsageLimitService
from .serializers import UsageLimitSerializer
from .service import UsageLimitService


class UsageLimitView(views.APIView):
    """
    API endpoint for retrieving user's usage limits
    """

    permission_classes = [AllowAny]

    def get(self, request):
        if request.user.is_authenticated:
            limit = UsageLimitService.get_or_create_usage_limit(request.user)
            limit_info = UsageLimitService.check_request_limit(request.user)
            serializer = UsageLimitSerializer(limit)
            data = serializer.data
            data.update(limit_info)

            return Response(data)
        else:
            x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
            if x_forwarded_for:
                ip_address = x_forwarded_for.split(",")[0].strip()
            else:
                ip_address = request.META.get("REMOTE_ADDR")
            limit = AnonymousUsageLimitService.get_or_create_anonymous_usage_limit(ip_address)
            limit_info = AnonymousUsageLimitService.check_anonymous_request_limit(ip_address)

            serializer = AnonymousUsageLimitSerializer(limit)
            data = serializer.data
            data.update(limit_info)

            return Response(data)