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
            # Proper initialization using Django Social Auth strategy
            strategy = load_strategy(request)
            backend = load_backend(strategy, provider, None)

            code_verifier = request.data.get("code_verifier")
            redirect_uri = request.data.get("redirect_uri")
            
            # Save code_verifier in strategy session for PKCE
            if code_verifier:
                strategy.session_set('code_verifier', code_verifier)
            
            # Pass redirect_uri to backend for correct token exchange
            if redirect_uri:
                backend.data = backend.data or {}
                backend.data['redirect_uri'] = redirect_uri
                backend.redirect_uri = redirect_uri
            
            # Perform authentication - pass authorization code
            user = backend.do_auth(code, code_verifier=code_verifier)
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
