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
    Custom pipeline step to associate existing users by google_id or email.
    
    This step handles the scenario where different Google Client IDs are used
    (e.g., regular OAuth2 vs One Tap), which may result in different google_id
    values for the same user. We use email as a fallback identifier.
    
    Process:
    1. If user is already found by social_user step, skip this step
    2. If backend is google-oauth2:
       a. Try to find user by google_id from response
       b. If not found, try to find by email (Google email is verified)
       c. If found by email, update the user's google_id
    3. Return the user to be associated in the next pipeline step
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
    
    # Try to get google_id and email from response
    response = kwargs.get('response', {})
    google_id = response.get('sub')  # Google uses 'sub' as user ID in OAuth2
    email = details.get('email')
    
    if not google_id:
        logger.warning("No google_id (sub) found in OAuth2 response")
        return None
    
    logger.info(f"Checking if user exists with google_id: {google_id} or email: {email}")
    
    # Try to find existing user by google_id
    from apps.users.models import User
    
    # Step 1: Try to find by google_id (primary identifier)
    existing_user = User.objects.filter(google_id=google_id).first()
    
    if existing_user:
        logger.info(f"Found existing user by google_id: {existing_user.email} (id={existing_user.id})")
        return {
            'user': existing_user,
            'is_new': False
        }
    
    # Step 2: If not found by google_id, try to find by email
    if email:
        existing_user = User.objects.filter(email=email).first()
        
        if existing_user:
            logger.info(f"Found existing user by email: {existing_user.email} (id={existing_user.id})")
            logger.info(f"Updating user's google_id from '{existing_user.google_id}' to '{google_id}'")
            
            # Update google_id for this user
            existing_user.google_id = google_id
            existing_user.save(update_fields=['google_id'])
            
            return {
                'user': existing_user,
                'is_new': False
            }
    
    # Step 3: User not found - continue with normal flow (will create new user)
    logger.info(f"No existing user found with google_id '{google_id}' or email '{email}' - will create new user")
    return None


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


def save_avatar_url(backend, user, response, *args, **kwargs):
    """
    Save avatar URL to User model after successful authentication.
    
    Extracts avatar URL from the provider's response and saves it
    to User.avatar_url. Updates on every login to keep the URL fresh.
    
    Supported providers:
        - google-oauth2: response['picture']
        - twitter-oauth2: response['data']['profile_image_url']
    
    Args:
        backend: The social auth backend instance
        user: User instance
        response: OAuth2 response from provider
        *args, **kwargs: Additional arguments from pipeline
    """
    avatar_url = None

    if backend.name == 'google-oauth2':
        avatar_url = response.get('picture')
    elif backend.name == 'twitter-oauth2':
        avatar_url = response.get('data', {}).get('profile_image_url')

    if avatar_url and avatar_url != user.avatar_url:
        logger.info(f"Updating avatar_url for user {user.email}: {avatar_url}")
        user.avatar_url = avatar_url
        user.save(update_fields=['avatar_url'])

    return None
