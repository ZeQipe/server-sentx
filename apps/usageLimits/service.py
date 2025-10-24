from datetime import date
from typing import Any

from apps.payments.models import Subscription
from .models import UsageLimit


class UsageLimitService:
    """Service for handling usage limits for authenticated users"""

    @staticmethod
    def get_or_create_usage_limit(user) -> UsageLimit:
        """Get or create usage limit for a user"""
        limit, _ = UsageLimit.objects.get_or_create(user=user)

        today = date.today()

        if limit.last_reset_date != today:
            limit.requests_made_today = 0
            limit.last_reset_date = today
            limit.save()

        return limit

    @staticmethod
    def check_request_limit(user) -> dict[str, Any]:
        """Check if user has reached their request limit"""
        limit = UsageLimitService.get_or_create_usage_limit(user)

        has_active_subscription = Subscription.objects.filter(
            user=user, is_active=True
        ).exists()

        daily_limit = (
            limit.paid_requests_limit
            if has_active_subscription
            else limit.free_requests_limit
        )
        requests_left = daily_limit - limit.requests_made_today

        can_make_request = limit.requests_made_today < daily_limit

        if user.is_unlimited:
            can_make_request = True

        return {
            "can_make_request": can_make_request,
            "requests_left": requests_left if not user.is_unlimited else 999_999_999,
            "has_subscription": has_active_subscription if not user.is_unlimited else True,
            "daily_limit": daily_limit if not user.is_unlimited else 999_999_999,
        }

    @staticmethod
    def increment_request_count(user) -> None:
        """Increment the request count for a user"""
        limit = UsageLimitService.get_or_create_usage_limit(user)
        limit.requests_made_today += 1
        limit.save()
