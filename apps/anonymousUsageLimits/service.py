from datetime import date
from typing import Any

from .models import AnonymousUsageLimit


class AnonymousUsageLimitService:
    """Service for handling usage limits for anonymous users"""

    @staticmethod
    def get_or_create_anonymous_usage_limit(ip_address) -> AnonymousUsageLimit:
        """Get or create usage limit for an anonymous user by IP address"""
        today = date.today()
        limit, _ = AnonymousUsageLimit.objects.get_or_create(
            ip_address=ip_address, last_reset_date=today
        )
        if limit.last_reset_date != today:
            limit.requests_made_today = 0
            limit.last_reset_date = today
            limit.save()
        return limit

    @staticmethod
    def check_anonymous_request_limit(ip_address) -> dict[str, Any]:
        """Check if anonymous user (by IP) has reached their request limit"""
        limit = AnonymousUsageLimitService.get_or_create_anonymous_usage_limit(ip_address)
        daily_limit = 3
        requests_left = daily_limit - limit.requests_made_today
        can_make_request = limit.requests_made_today < daily_limit
        return {
            "can_make_request": can_make_request,
            "requests_left": requests_left,
            "daily_limit": daily_limit,
        }

    @staticmethod
    def increment_anonymous_request_count(ip_address) -> None:
        """Increment the request count for an anonymous user by IP address"""
        limit = AnonymousUsageLimitService.get_or_create_anonymous_usage_limit(ip_address)
        limit.requests_made_today += 1
        limit.save()
