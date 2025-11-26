import logging
from django.conf import settings
from django.utils.module_loading import import_string
from rest_framework import generics, response, status
from rest_framework_simplejwt.tokens import RefreshToken
from social_core.backends.oauth import BaseOAuth2
from social_core.exceptions import AuthCanceled, AuthForbidden, AuthException
from social_django.utils import load_strategy, load_backend

from apps.users.models import User

logger = logging.getLogger(__name__)


class SocialAuthCallbackView(generics.GenericAPIView):
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
                return response.Response(
                    data={
                        "access_token": str(refresh.access_token),
                        "refresh_token": str(refresh),
                        "user_id": user.id,
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


class GoogleOneTapView(generics.GenericAPIView):
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
            
            # 4. Check if email is already taken by another user (without google_id)
            existing_user_with_email = User.objects.filter(email=email).first()
            if existing_user_with_email and not existing_user_with_email.google_id:
                return response.Response(
                    data={"detail": "Этот почтовый ящик уже занят другим аккаунтом"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            
            # 5. Get or create user by google_id
            # Данные обновляются ТОЛЬКО при создании (created=True)
            user, created = User.objects.get_or_create(
                google_id=google_id,
                defaults={
                    'email': email,
                    'name': given_name if given_name else email.split('@')[0],
                }
            )
            
            logger.info(f"Google One Tap auth successful for user {user.id} (created={created})")
            
            # 6. Generate JWT tokens
            refresh = RefreshToken.for_user(user)
            
            return response.Response(
                data={
                    "access": str(refresh.access_token),
                    "refresh": str(refresh),
                    "user": {
                        "id": user.id,
                        "email": user.email,
                        "name": user.name,
                    }
                },
                status=status.HTTP_200_OK,
            )
            
        except Exception as e:
            logger.error(f"Error during Google One Tap auth: {str(e)}", exc_info=True)
            return response.Response(
                data={"detail": f"Authentication error: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )