from django.conf import settings
from django.contrib.auth import get_user_model
from google.auth.exceptions import GoogleAuthError as GoogleLibraryAuthError
from google.auth.transport.requests import Request
from google.oauth2 import id_token
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import RefreshToken


class GoogleAuthConfigurationError(Exception):
    pass


class GoogleAuthError(Exception):
    pass


def build_login_response(user, google_user=None, is_new_user=False):
    if hasattr(user, 'refresh_expired_suspension'):
        user.refresh_expired_suspension(save=True)
    if not user.is_active:
        message = (
            user.account_unavailable_message()
            if hasattr(user, 'account_unavailable_message')
            else 'Your account is not active.'
        )
        raise AuthenticationFailed(message)

    user_name = ''
    if hasattr(user, 'get_full_name'):
        user_name = user.get_full_name()

    refresh = RefreshToken.for_user(user)
    access = refresh.access_token
    if hasattr(user, 'active_token'):
        user.active_token = access['jti']
        user.save(update_fields=['active_token'])

    return {
        'refresh': str(refresh),
        'access': str(access),
        'user': {
            'id': user.id,
            'email': user.email,
            'name': (
                (google_user or {}).get('name')
                or user_name
                or getattr(user, 'username', '')
                or str(user)
            ),
            'picture': (google_user or {}).get('picture'),
            'is_new_user': is_new_user,
        },
    }


def build_unique_username(email):
    User = get_user_model()
    base = email.split('@')[0].strip().lower() or 'google-user'
    base = ''.join(char if char.isalnum() or char in '._-' else '-' for char in base)
    username = base[:130]
    suffix = 1

    while User.objects.filter(username=username).exists():
        suffix_text = f"-{suffix}"
        username = f"{base[:150 - len(suffix_text)]}{suffix_text}"
        suffix += 1

    return username


def verify_google_id_token(credential):
    if not settings.GOOGLE_CLIENT_ID:
        raise GoogleAuthConfigurationError('GOOGLE_CLIENT_ID is not configured.')

    try:
        data = id_token.verify_oauth2_token(
            credential,
            Request(),
            settings.GOOGLE_CLIENT_ID,
        )
    except (ValueError, GoogleLibraryAuthError) as exc:
        raise GoogleAuthError('Google credential could not be verified.') from exc

    if not data.get('email'):
        raise GoogleAuthError('Google credential does not include an email.')
    if data.get('email_verified') not in [True, 'true', 'True', '1', 1]:
        raise GoogleAuthError('Google account email is not verified.')

    return data
