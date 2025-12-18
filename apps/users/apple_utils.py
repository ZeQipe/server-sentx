"""
Утилиты для работы с Apple OAuth2
Адаптировано из референсной реализации temp-content
"""
import jwt
import time
import logging
import httpx
from typing import Dict, Any
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from django.conf import settings

logger = logging.getLogger(__name__)


def generate_client_secret() -> str:
    """
    Генерирует client_secret для Apple OAuth2.
    Apple требует JWT токен, подписанный вашим приватным ключом (.p8)
    
    Returns:
        str: JWT токен (client_secret)
    """
    # Время создания и истечения токена
    now = int(time.time())
    expiration = now + (86400 * 180)  # 180 дней (максимум 6 месяцев)
    
    # Заголовки JWT
    headers = {
        "kid": settings.APPLE_KEY_ID,  # Key ID из Apple Developer
        "alg": "ES256"  # Алгоритм подписи (ECDSA с SHA-256)
    }
    
    # Payload JWT
    payload = {
        "iss": settings.APPLE_TEAM_ID,  # Issuer - ваш Team ID
        "iat": now,  # Issued At - время создания
        "exp": expiration,  # Expiration - время истечения
        "aud": "https://appleid.apple.com",  # Audience - всегда это значение
        "sub": settings.APPLE_CLIENT_ID  # Subject - ваш Client ID (Services ID)
    }
    
    # Загружаем приватный ключ из настроек
    # Конвертируем \n в реальные переносы строк (для переменных окружения)
    try:
        private_key_str = settings.APPLE_PRIVATE_KEY.replace('\\n', '\n')
        private_key = serialization.load_pem_private_key(
            private_key_str.encode(),
            password=None,
            backend=default_backend()
        )
    except Exception as e:
        logger.error(f"Ошибка загрузки приватного ключа Apple: {e}")
        raise ValueError(f"Ошибка загрузки приватного ключа: {e}")
    
    # Генерируем и подписываем JWT
    client_secret = jwt.encode(
        payload,
        private_key,
        algorithm="ES256",
        headers=headers
    )
    
    return client_secret


async def exchange_code_for_tokens(code: str) -> Dict[str, Any]:
    """
    Обменивает authorization code на токены от Apple.
    
    Args:
        code: Authorization code от Apple
        
    Returns:
        Dict с токенами (access_token, id_token, refresh_token)
    """
    client_secret = generate_client_secret()
    
    data = {
        "client_id": settings.APPLE_CLIENT_ID,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": settings.APPLE_REDIRECT_URI
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://appleid.apple.com/auth/token",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        if response.status_code != 200:
            logger.error(f"Apple token exchange failed: {response.text}")
            raise Exception(f"Ошибка получения токенов от Apple: {response.text}")
        
        return response.json()


def exchange_code_for_tokens_sync(code: str) -> Dict[str, Any]:
    """
    Синхронная версия обмена authorization code на токены.
    Используется в Django views.
    
    Args:
        code: Authorization code от Apple
        
    Returns:
        Dict с токенами (access_token, id_token, refresh_token)
    """
    client_secret = generate_client_secret()
    
    data = {
        "client_id": settings.APPLE_CLIENT_ID,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": settings.APPLE_REDIRECT_URI
    }
    
    with httpx.Client() as client:
        response = client.post(
            "https://appleid.apple.com/auth/token",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        if response.status_code != 200:
            logger.error(f"Apple token exchange failed: {response.text}")
            raise Exception(f"Ошибка получения токенов от Apple: {response.text}")
        
        return response.json()


def decode_id_token(id_token: str) -> Dict[str, Any]:
    """
    Декодирует ID токен от Apple.
    
    Примечание: В production рекомендуется проверять подпись через Apple Public Keys.
    Для простоты здесь используется декодирование без проверки подписи.
    
    Args:
        id_token: JWT токен от Apple
        
    Returns:
        Dict с данными пользователя (sub, email, email_verified, is_private_email)
    """
    try:
        # Декодируем без проверки подписи
        # В production нужно проверять подпись через Apple Public Keys
        decoded = jwt.decode(
            id_token,
            options={"verify_signature": False}
        )
        return decoded
    except Exception as e:
        logger.error(f"Ошибка декодирования Apple ID токена: {e}")
        raise ValueError(f"Ошибка декодирования ID токена: {e}")


def validate_id_token_full(id_token: str) -> Dict[str, Any]:
    """
    Полная валидация ID токена с проверкой базовых полей.
    
    Для production рекомендуется также проверять подпись через Apple Public Keys.
    
    Args:
        id_token: JWT токен от Apple
        
    Returns:
        Dict с данными пользователя
    """
    decoded = decode_id_token(id_token)
    
    # Проверяем issuer
    if decoded.get('iss') != 'https://appleid.apple.com':
        raise ValueError("Неверный issuer в токене")
    
    # Проверяем audience
    if decoded.get('aud') != settings.APPLE_CLIENT_ID:
        raise ValueError("Неверный audience в токене")
    
    # Проверяем срок действия
    if decoded.get('exp', 0) < time.time():
        raise ValueError("Токен истёк")
    
    return decoded
