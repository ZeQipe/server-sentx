from datetime import date
from typing import Any, Optional

from .models import AnonymousUsageLimit


class AnonymousUsageLimitService:
    """Service for handling usage limits for anonymous users"""

    @staticmethod
    def get_or_create_anonymous_usage_limit(
        ip_address: str,
        fingerprint_hash: Optional[str] = None
    ) -> AnonymousUsageLimit:
        """
        Get or create usage limit for an anonymous user
        
        Приоритет поиска:
        1. По fingerprint_hash (если передан)
        2. По ip_address (fallback)
        
        Args:
            ip_address: IP адрес пользователя
            fingerprint_hash: Хэш устройства (опционально)
            
        Returns:
            AnonymousUsageLimit объект
        """
        today = date.today()
        
        # Пытаемся найти по fingerprint_hash (если передан)
        if fingerprint_hash:
            limit = AnonymousUsageLimit.objects.filter(
                fingerprint=fingerprint_hash,
                last_reset_date=today
            ).first()
            
            if limit:
                # Проверяем дату на всякий случай
                if limit.last_reset_date != today:
                    limit.requests_made_today = 0
                    limit.last_reset_date = today
                    limit.save()
                return limit
        
        # Fallback: ищем по IP или создаем новый
        limit, created = AnonymousUsageLimit.objects.get_or_create(
            ip_address=ip_address,
            last_reset_date=today,
            defaults={
                'fingerprint': fingerprint_hash,
                'requests_made_today': 0
            }
        )
        
        if not created and limit.last_reset_date != today:
            limit.requests_made_today = 0
            limit.last_reset_date = today
            limit.save()
        
        # Если fingerprint был передан, но не был сохранен - обновляем
        if fingerprint_hash and not limit.fingerprint:
            limit.fingerprint = fingerprint_hash
            limit.save(update_fields=['fingerprint'])
            
        return limit

    @staticmethod
    def check_anonymous_request_limit(ip_address) -> dict[str, Any]:
        """Check if anonymous user (by IP) has reached their request limit"""
        limit = AnonymousUsageLimitService.get_or_create_anonymous_usage_limit(ip_address)
        daily_limit = 10
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
