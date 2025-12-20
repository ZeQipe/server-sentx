import logging
import secrets
from urllib.parse import urlencode

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponseRedirect
from django.utils.decorators import method_decorator
from django.utils.module_loading import import_string
from django.views.decorators.csrf import csrf_exempt
from rest_framework import response, status
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from social_core.backends.oauth import BaseOAuth2
from social_core.exceptions import AuthCanceled, AuthForbidden, AuthException
from social_django.utils import load_strategy, load_backend

from apps.users.models import User

logger = logging.getLogger(__name__)

# Cache timeout для Apple OAuth state и session (5 минут)
APPLE_STATE_TIMEOUT = 300
APPLE_SESSION_TIMEOUT = 300


class SocialAuthCallbackView(APIView):
    """Handle OAuth2 callback from social provider and generate JWT tokens."""

    def post(self, request, provider):
        """Handle OAuth2 callback specifically for the provided social provider."""
        code = request.data.get("code")
        return self.handle_auth(request, code, provider)

    def handle_auth(self, request, code, provider):
        """Handle authentication for the provided social provider."""
        try:
            logger.info(f"Starting handle_auth for provider: {provider}")
            
            # Proper initialization using Django Social Auth strategy
            strategy = load_strategy(request)
            logger.info(f"Strategy loaded: {strategy}")
            
            backend = load_backend(strategy, provider, None)
            logger.info(f"Backend loaded: {backend}")

            code_verifier = request.data.get("code_verifier")
            redirect_uri = request.data.get("redirect_uri")
            logger.info(f"Code verifier: {code_verifier[:20]}..." if code_verifier else "No code_verifier")
            logger.info(f"Redirect URI: {redirect_uri}")
            
            # Save code_verifier in strategy session for PKCE
            if code_verifier:
                strategy.session_set('code_verifier', code_verifier)
            
            # Pass redirect_uri to backend for correct token exchange
            if redirect_uri:
                backend.data = backend.data or {}
                backend.data['redirect_uri'] = redirect_uri
                backend.redirect_uri = redirect_uri
            
            logger.info(f"Calling backend.do_auth with code...")
            # Perform authentication - pass authorization code
            user = backend.do_auth(code, code_verifier=code_verifier)
            logger.info(f"User returned: {user}")
            if user:
                refresh = RefreshToken.for_user(user)
                # Определяем auth_provider
                auth_provider = None
                if user.google_id:
                    auth_provider = "google"
                elif user.icloud_id:
                    auth_provider = "apple"
                elif user.x_id:
                    auth_provider = "x"
                return response.Response(
                    data={
                        "access_token": str(refresh.access_token),
                        "refresh_token": str(refresh),
                        "user_id": user.id,
                        "auth_provider": auth_provider,
                    },
                    status=status.HTTP_200_OK,
                )
            else:
                logger.error("Authentication failed - no user returned")
                return response.Response(
                    data={"detail": ["Authentication failed."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        except AuthCanceled:
            logger.error("Authentication canceled by user")
            return response.Response(
                data={"detail": ["Authentication canceled."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except AuthForbidden as e:
            logger.error(f"AuthForbidden error: {str(e)}")
            return response.Response(
                data={"detail": ["Your credentials aren't allowed"]},
                status=status.HTTP_403_FORBIDDEN,
            )
        except AuthException as e:
            logger.error(f"AuthException error: {str(e)}")
            return response.Response(
                data={"detail": [f"Authentication error: {str(e)}"]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.error(f"Error during social auth: {str(e)}", exc_info=True)
            return response.Response(
                data={"detail": [f"An error occurred while authenticating: {str(e)}"]},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


def get_backend(provider):
    """Get the backend class path based on the provider."""
    backend_mapping = {
        "google-oauth2": "apps.users.backends.CustomGoogleOAuth2",
        "twitter-oauth2": "apps.users.backends.CustomTwitterOAuth2",
    }

    backend_class = backend_mapping.get(provider)
    if backend_class:
        return backend_class
    raise ValueError(f"Unknown provider: {provider}")


class GoogleOneTapView(APIView):
    """Handle Google One Tap authentication and generate JWT tokens."""
    
    permission_classes = []  # Allow any - no authentication required
    authentication_classes = []  # Disable authentication for this endpoint

    def post(self, request):
        """
        Verify Google One Tap ID token and return JWT tokens.
        
        Expects:
            {
                "credentials": "<google_id_token>"
            }
        
        Returns:
            {
                "access": "jwt_access_token",
                "refresh": "jwt_refresh_token",
                "user": {
                    "id": user_id,
                    "email": "user@example.com",
                    "name": "User Name"
                }
            }
        """
        from google.oauth2 import id_token
        from google.auth.transport import requests as google_requests
        
        try:
            # 1. Extract token from request body
            token = request.data.get('credentials')
            if not token:
                return response.Response(
                    data={"detail": "credentials field is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            
            # 2. Verify Google ID token
            try:
                payload = id_token.verify_oauth2_token(
                    token,
                    google_requests.Request(),
                    settings.ONE_TAP_GOOGLE_CLIENT_ID,
                    clock_skew_in_seconds=60  # Допустимое отклонение времени 60 секунд
                )
            except ValueError as e:
                logger.error(f"Invalid Google token: {str(e)}")
                return response.Response(
                    data={"detail": "Invalid Google token"},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            
            # 3. Extract user data from payload
            google_id = payload.get('sub')
            email = payload.get('email')
            given_name = payload.get('given_name', '')
            family_name = payload.get('family_name', '')
            picture = payload.get('picture', '')
            
            if not google_id or not email:
                return response.Response(
                    data={"detail": "Invalid token payload: missing required fields"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            
            # 4. Find or create user - strategy with email fallback
            # Сначала ищем по google_id (основной идентификатор)
            user = User.objects.filter(google_id=google_id).first()
            created = False
            
            if user:
                logger.info(f"Found existing user by google_id: {user.email} (id={user.id})")
            else:
                # Если не нашли по google_id, ищем по email
                user = User.objects.filter(email=email).first()
                
                if user:
                    logger.info(f"Found existing user by email: {user.email} (id={user.id}), updating google_id")
                    # Обновляем google_id для этого пользователя
                    user.google_id = google_id
                    user.save(update_fields=['google_id'])
                else:
                    # Пользователя нет - создаем нового
                    logger.info(f"Creating new user with email: {email}, google_id: {google_id}")
                    user = User.objects.create(
                        email=email,
                        google_id=google_id,
                        name=given_name if given_name else email.split('@')[0],
                    )
                    created = True
            
            logger.info(f"Google One Tap auth successful for user {user.id} (created={created})")
            
            # 6. Generate JWT tokens
            refresh = RefreshToken.for_user(user)
            
            return response.Response(
                data={
                    "access_token": str(refresh.access_token),
                    "refresh_token": str(refresh),
                    "user_id": user.id,
                    "auth_provider": "google",
                },
                status=status.HTTP_200_OK,
            )
            
        except Exception as e:
            logger.error(f"Error during Google One Tap auth: {str(e)}", exc_info=True)
            return response.Response(
                data={"detail": f"Authentication error: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# ============================================================================
# Apple OAuth2 Views
# ============================================================================

class AppleLoginView(APIView):
    """
    Инициация Apple OAuth2 flow.
    Возвращает URL для редиректа на страницу авторизации Apple.
    
    GET /api/auth/custom/apple/login/
    
    Response:
        {
            "auth_url": "https://appleid.apple.com/auth/authorize?...",
            "message": "Перейдите по auth_url для авторизации"
        }
    """
    permission_classes = []
    authentication_classes = []

    def get(self, request):
        try:
            # Генерируем уникальный state для защиты от CSRF
            state = secrets.token_urlsafe(32)
            
            # Сохраняем state в cache
            cache.set(f"apple_state_{state}", True, APPLE_STATE_TIMEOUT)
            
            # Параметры для Apple OAuth
            params = {
                "client_id": settings.APPLE_CLIENT_ID,
                "redirect_uri": settings.APPLE_REDIRECT_URI,
                "response_type": "code",
                "response_mode": "form_post",  # Apple отправит POST запрос
                "state": state,
                "scope": "name email",
            }
            
            # Строим URL для редиректа
            auth_url = f"https://appleid.apple.com/auth/authorize?{urlencode(params)}"
            
            return response.Response(
                data={
                    "auth_url": auth_url,
                    "message": "Перейдите по auth_url для авторизации"
                },
                status=status.HTTP_200_OK,
            )
            
        except Exception as e:
            logger.error(f"Error in AppleLoginView: {str(e)}", exc_info=True)
            return response.Response(
                data={"detail": f"Ошибка инициализации Apple OAuth: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@method_decorator(csrf_exempt, name='dispatch')
class AppleCallbackView(APIView):
    """
    Обработка callback от Apple после авторизации.
    Apple отправляет POST запрос с code и state (response_mode=form_post).
    
    POST /api/auth/custom/apple/callback/
    
    ВАЖНО: CSRF отключен, т.к. Apple делает POST запрос напрямую.
    
    После успешной обработки редиректит на frontend с session_id.
    """
    permission_classes = []
    authentication_classes = []

    def post(self, request):
        return self._handle_callback(request)
    
    def get(self, request):
        return self._handle_callback(request)

    def _handle_callback(self, request):
        from apps.users.apple_utils import exchange_code_for_tokens_sync, decode_id_token
        
        try:
            # Apple может отправить POST или GET
            if request.method == "POST":
                code = request.POST.get("code") or request.data.get("code")
                state = request.POST.get("state") or request.data.get("state")
                user_data = request.POST.get("user") or request.data.get("user")
                error = request.POST.get("error") or request.data.get("error")
            else:
                code = request.GET.get("code")
                state = request.GET.get("state")
                user_data = request.GET.get("user")
                error = request.GET.get("error")
            
            logger.info(f"Apple callback received: code={'yes' if code else 'no'}, state={state}, error={error}")
            
            # Проверяем на ошибки от Apple
            if error:
                logger.error(f"Apple OAuth error: {error}")
                return HttpResponseRedirect(
                    f"{settings.APPLE_FRONTEND_CALLBACK_URL}?error={error}"
                )
            
            # Проверяем state (защита от CSRF)
            if not state or not cache.get(f"apple_state_{state}"):
                logger.error(f"Invalid or expired state: {state}")
                return HttpResponseRedirect(
                    f"{settings.APPLE_FRONTEND_CALLBACK_URL}?error=invalid_state"
                )
            
            # Удаляем использованный state
            cache.delete(f"apple_state_{state}")
            
            if not code:
                logger.error("Missing authorization code")
                return HttpResponseRedirect(
                    f"{settings.APPLE_FRONTEND_CALLBACK_URL}?error=missing_code"
                )
            
            # Обмениваем code на токены
            tokens = exchange_code_for_tokens_sync(code)
            
            # Декодируем ID токен
            id_token = tokens.get("id_token")
            if not id_token:
                logger.error("Missing id_token in Apple response")
                return HttpResponseRedirect(
                    f"{settings.APPLE_FRONTEND_CALLBACK_URL}?error=missing_id_token"
                )
            
            user_info = decode_id_token(id_token)
            apple_user_id = user_info.get("sub")
            email = user_info.get("email")
            email_verified = user_info.get("email_verified", False)
            is_private_email = user_info.get("is_private_email", False)
            
            logger.info(f"Apple user authenticated: apple_id={apple_user_id}, email={email}")
            
            # Создаём сессию с данными пользователя
            session_id = secrets.token_urlsafe(32)
            session_data = {
                "apple_user_id": apple_user_id,
                "email": email,
                "email_verified": email_verified,
                "is_private_email": is_private_email,
                "tokens": tokens,
                "user_data": user_data,  # Может быть None при повторных входах
            }
            
            # Сохраняем в cache
            cache.set(f"apple_session_{session_id}", session_data, APPLE_SESSION_TIMEOUT)
            
            # Редиректим на frontend с sessionid
            redirect_url = f"{settings.APPLE_FRONTEND_CALLBACK_URL}?sessionid={session_id}"
            return HttpResponseRedirect(redirect_url)
            
        except Exception as e:
            logger.error(f"Error in AppleCallbackView: {str(e)}", exc_info=True)
            return HttpResponseRedirect(
                f"{settings.APPLE_FRONTEND_CALLBACK_URL}?error=authentication_failed"
            )


class AppleUserView(APIView):
    """
    Получение данных пользователя по sessionid.
    Формат ответа идентичен тестовому примеру + JWT токены.
    
    GET /api/auth/custom/apple/user/?sessionid=XXX
    
    Response:
        {
            "access_token": "eyJ...",
            "refresh_token": "eyJ...",
            "user_id": "001234.abcdef...",
            "email": "user@example.com",
            "email_verified": true,
            "is_private_email": false
        }
    """
    permission_classes = []
    authentication_classes = []

    def get(self, request):
        try:
            session_id = request.GET.get("sessionid")
            
            if not session_id:
                return response.Response(
                    data={"detail": "sessionid is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            
            # Получаем данные сессии из cache
            session_data = cache.get(f"apple_session_{session_id}")
            
            if not session_data:
                return response.Response(
                    data={"detail": "Неверная или истекшая сессия"},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            
            # Удаляем использованную сессию (одноразовая)
            cache.delete(f"apple_session_{session_id}")
            
            apple_user_id = session_data.get("apple_user_id")
            email = session_data.get("email")
            email_verified = session_data.get("email_verified")
            is_private_email = session_data.get("is_private_email")
            
            if not apple_user_id:
                return response.Response(
                    data={"detail": "Invalid session data"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            
            # Ищем или создаём пользователя в БД
            # Стратегия: сначала по icloud_id (Apple ID), потом по email
            user = User.objects.filter(icloud_id=apple_user_id).first()
            created = False
            
            if user:
                logger.info(f"Found existing user by icloud_id: {user.email} (id={user.id})")
            else:
                # Если не нашли по icloud_id, ищем по email
                if email:
                    user = User.objects.filter(email=email).first()
                    
                    if user:
                        logger.info(f"Found existing user by email: {user.email} (id={user.id}), updating icloud_id")
                        # Обновляем icloud_id для этого пользователя
                        user.icloud_id = apple_user_id
                        user.save(update_fields=['icloud_id'])
                    else:
                        # Пользователя нет - создаём нового
                        logger.info(f"Creating new user with email: {email}, icloud_id: {apple_user_id}")
                        user = User.objects.create(
                            email=email,
                            icloud_id=apple_user_id,
                            name=email.split('@')[0] if email else "Apple User",
                        )
                        created = True
                else:
                    # Email не передан (возможно при повторных входах)
                    # Создаём пользователя с placeholder email
                    placeholder_email = f"apple_{apple_user_id[:8]}@privaterelay.appleid.com"
                    logger.info(f"Creating new user without email, using placeholder: {placeholder_email}")
                    user = User.objects.create(
                        email=placeholder_email,
                        icloud_id=apple_user_id,
                        name="Apple User",
                    )
                    created = True
            
            logger.info(f"Apple auth successful for user {user.id} (created={created})")
            
            # Генерируем JWT токены для пользователя
            refresh = RefreshToken.for_user(user)
            
            # Возвращаем данные пользователя + JWT токены
            return response.Response(
                data={
                    "access_token": str(refresh.access_token),
                    "refresh_token": str(refresh),
                    "user_id": apple_user_id,
                    "email": email,
                    "email_verified": email_verified,
                    "is_private_email": is_private_email,
                    "auth_provider": "apple",
                },
                status=status.HTTP_200_OK,
            )
            
        except Exception as e:
            logger.error(f"Error in AppleUserView: {str(e)}", exc_info=True)
            return response.Response(
                data={"detail": f"Authentication error: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )