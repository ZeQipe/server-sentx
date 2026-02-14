import logging

import requests
from social_core.backends.google import GoogleOAuth2
from social_core.backends.twitter_oauth2 import TwitterOAuth2
from social_core.exceptions import AuthTokenError

logger = logging.getLogger(__name__)


class CustomGoogleOAuth2(GoogleOAuth2):
    """Custom Google OAuth2 backend with enhanced error handling."""

    name = "google-oauth2"

    def get_access_token(self, code, code_verifier=None):
        """Exchange authorization code for access token."""
        token_url = "https://oauth2.googleapis.com/token"

        # Get redirect_uri from request data or use default value
        redirect_uri = (
            self.data.get("redirect_uri")
            or self.redirect_uri
            or "http://localhost:5173/auth/google/callback"
        )

        data = {
            "client_id": self.setting("KEY"),
            "client_secret": self.setting("SECRET"),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }

        # Add PKCE code verifier if available
        if code_verifier:
            data["code_verifier"] = code_verifier

        try:
            response = requests.post(token_url, data=data)
            response.raise_for_status()

            token_data = response.json()
            return token_data

        except requests.exceptions.RequestException as e:
            logger.error(f"Token exchange request failed: {str(e)}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response status: {e.response.status_code}")
                logger.error(f"Response content: {e.response.text}")
            raise

    def do_auth(self, access_token, *args, **kwargs):
        """Custom authentication handler with proper token handling."""

        # Check if this is an authorization code (starts with 4/)
        if access_token.startswith("4/"):
            # Get the code verifier from the session or request
            code_verifier = kwargs.get("code_verifier") or self.strategy.session_get(
                "code_verifier"
            )

            # Exchange authorization code for access token
            try:
                token_data = self.get_access_token(access_token, code_verifier)
                if token_data and "access_token" in token_data:
                    actual_access_token = token_data["access_token"]

                    # Now use the actual access token
                    return super().do_auth(actual_access_token, *args, **kwargs)
                else:
                    logger.error(
                        "Failed to exchange authorization code for access token"
                    )
                    raise AuthTokenError(self, "Failed to exchange authorization code")

            except Exception as e:
                logger.error(f"Error exchanging authorization code: {str(e)}")
                raise AuthTokenError(self, f"Token exchange error: {str(e)}")

        try:
            return super().do_auth(access_token, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error in do_auth: {str(e)}")
            raise AuthTokenError(self, f"Token error: {str(e)}")

    def user_data(self, access_token, *args, **kwargs):
        """Get user data from Google API."""
        try:
            response = self.get_json(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            return response

        except Exception as e:
            logger.error(f"HTTP Error getting user data: {str(e)}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response status: {e.response.status_code}")
                logger.error(f"Response content: {e.response.text}")

            logger.error("Access token is invalid or expired")
            raise AuthTokenError(self, "Invalid or expired access token")

    def auth_complete(self, *args, **kwargs):
        """Complete authentication with error handling."""
        try:
            return super().auth_complete(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in auth_complete: {e}", exc_info=True)
            raise

    def get_user_details(self, response):
        """Extract user details from Google OAuth response."""
        email = response.get("email", "")
        first_name = response.get("given_name", "")

        return {
            "email": email,
            "name": first_name,
        }


class CustomTwitterOAuth2(TwitterOAuth2):
    """Custom Twitter OAuth2 backend with enhanced error handling."""

    name = "twitter-oauth2"

    def get_access_token(self, code, code_verifier=None):
        """Exchange authorization code for access token."""
        token_url = "https://api.twitter.com/2/oauth2/token"
        redirect_uri = (
            self.data.get("redirect_uri")
            or self.redirect_uri
            or "http://localhost:5173/auth/twitter/callback"
        )

        client_id = self.setting("KEY")
        client_secret = self.setting("SECRET")

        if not client_id or not client_secret:
            logger.error("Twitter OAuth2 credentials not configured")
            raise AuthTokenError(self, "Twitter OAuth2 credentials not configured")

        if not code_verifier:
            logger.error("Twitter OAuth2 requires code_verifier for PKCE")
            raise AuthTokenError(
                self, "PKCE code_verifier is required for Twitter OAuth2"
            )

        data = {
            "client_id": client_id,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
        }

        import base64

        credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        headers = {
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        try:
            response = requests.post(token_url, data=data, headers=headers)
            response.raise_for_status()
            token_data = response.json()
            return token_data

        except requests.exceptions.RequestException as e:
            logger.error(f"Twitter token exchange failed: {str(e)}")
            if hasattr(e, "response") and e.response is not None:
                if e.response.status_code == 400:
                    logger.error("TwitterOAuth2: 400 Bad Request")
                elif e.response.status_code == 401:
                    logger.error("TwitterOAuth2: 401 Unauthorized")
            raise

    def do_auth(self, access_token, *args, **kwargs):
        """Custom authentication handler for Twitter."""
        # Twitter authorization codes have a different format
        if len(access_token) > 40 and not access_token.startswith("Bearer"):
            code_verifier = kwargs.get("code_verifier") or self.strategy.session_get(
                "code_verifier"
            )

            try:
                token_data = self.get_access_token(access_token, code_verifier)
                if token_data and "access_token" in token_data:
                    actual_access_token = token_data["access_token"]
                    return super().do_auth(actual_access_token, *args, **kwargs)
                else:
                    logger.error("Failed to exchange Twitter authorization code")
                    raise AuthTokenError(self, "Failed to exchange authorization code")

            except Exception as e:
                logger.error(f"Error exchanging Twitter authorization code: {str(e)}")
                raise AuthTokenError(self, f"Token exchange error: {str(e)}")

        try:
            return super().do_auth(access_token, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error in Twitter do_auth: {str(e)}")
            raise AuthTokenError(self, f"Token error: {str(e)}")

    def user_data(self, access_token, *args, **kwargs):
        """Get user data from Twitter API with detailed error handling."""
        try:
            response = self.get_json(
                "https://api.twitter.com/2/users/me",
                params={"user.fields": "id,name,username,profile_image_url"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            return response

        except Exception as e:
            logger.error(f"Twitter user_data error: {str(e)}")

            logger.error(f"TwitterOAuth2: Failed to get user data: {str(e)}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(
                    f"TwitterOAuth2: HTTP {e.response.status_code}: {e.response.text}"
                )
            raise AuthTokenError(self, f"Failed to get Twitter user data: {str(e)}")

    def get_user_details(self, response):
        """Extract user details from Twitter OAuth response."""
        data = response.get("data", {})
        username = data.get("username", "")
        name = data.get("name", "")
        user_id = data.get("id", "")
        email = f"x_user_{user_id}@x.local" if user_id else "x_user@x.local"

        return {
            "email": email,
            "name": name or username or "X User",
        }
