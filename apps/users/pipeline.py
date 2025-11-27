"""
Custom pipeline steps for Django Social Auth.

This module contains custom pipeline functions that extend the default
social authentication flow to handle edge cases like One Tap authentication.
"""
import logging
from social_core.pipeline.partial import partial

logger = logging.getLogger(__name__)


def associate_by_google_id(backend, details, user=None, *args, **kwargs):
    """
    Custom pipeline step to associate existing users by google_id.
    
    This step is needed to handle the scenario where a user was created via
    Google One Tap (which only creates a User record with google_id) and later
    tries to authenticate via regular OAuth2 flow (which expects UserSocialAuth).
    
    Process:
    1. If user is already found by social_user step, skip this step
    2. If backend is google-oauth2, try to find user by google_id from response
    3. If user found, return it to be associated in the next pipeline step
    4. Otherwise, continue with normal flow (create new user)
    
    Args:
        backend: The social auth backend instance
        details: Dict with user details from the provider
        user: User instance if already found by previous pipeline steps
        *args, **kwargs: Additional arguments from pipeline
        
    Returns:
        Dict with 'user' key if user was found, otherwise None to continue pipeline
    """
    # If user already found (by email or social_user step), skip
    if user:
        logger.info(f"User already found in pipeline: {user.email}")
        return {'user': user}
    
    # Only handle Google OAuth2 backend
    if backend.name != 'google-oauth2':
        logger.info(f"Backend {backend.name} - skipping google_id association")
        return None
    
    # Try to get google_id from response
    response = kwargs.get('response', {})
    google_id = response.get('sub')  # Google uses 'sub' as user ID in OAuth2
    
    if not google_id:
        logger.warning("No google_id (sub) found in OAuth2 response")
        return None
    
    logger.info(f"Checking if user exists with google_id: {google_id}")
    
    # Try to find existing user by google_id
    from apps.users.models import User
    
    try:
        existing_user = User.objects.get(google_id=google_id)
        logger.info(f"Found existing user by google_id: {existing_user.email}")
        
        # Return the user to be associated with UserSocialAuth in next steps
        return {
            'user': existing_user,
            'is_new': False
        }
        
    except User.DoesNotExist:
        logger.info(f"No existing user found with google_id: {google_id}")
        # Continue with normal flow - will create new user
        return None
    except User.MultipleObjectsReturned:
        logger.error(f"Multiple users found with google_id: {google_id}")
        # In case of duplicate google_ids, use the first one
        existing_user = User.objects.filter(google_id=google_id).first()
        return {
            'user': existing_user,
            'is_new': False
        }


def save_google_id(backend, user, response, *args, **kwargs):
    """
    Save google_id to User model after successful authentication.
    
    This ensures that users created via OAuth2 flow also have google_id
    stored in the User model for consistency with One Tap authentication.
    
    Args:
        backend: The social auth backend instance
        user: User instance
        response: OAuth2 response from provider
        *args, **kwargs: Additional arguments from pipeline
    """
    # Only handle Google OAuth2 backend
    if backend.name != 'google-oauth2':
        return None
    
    # Get google_id from response
    google_id = response.get('sub')
    
    if not google_id:
        logger.warning("No google_id (sub) found in OAuth2 response")
        return None
    
    # Update user's google_id if not set or different
    if not user.google_id or user.google_id != google_id:
        logger.info(f"Updating google_id for user {user.email}: {google_id}")
        user.google_id = google_id
        user.save(update_fields=['google_id'])
    else:
        logger.info(f"User {user.email} already has correct google_id: {google_id}")
    
    return None

