import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import RefreshToken


class GoogleAuthConfigurationError(Exception):
    pass


class GoogleAuthError(Exception):
    pass


def build_login_response(user):
    user.refresh_expired_suspension(save=True)
    if not user.is_active:
        raise AuthenticationFailed(user.account_unavailable_message())

    refresh = RefreshToken.for_user(user)
    access = refresh.access_token
    user.active_token = access['jti']
    user.save(update_fields=['active_token'])

    return {
        'refresh': str(refresh),
        'access': str(access),
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

    response = requests.get(
        'https://oauth2.googleapis.com/tokeninfo',
        params={'id_token': credential},
        timeout=10,
    )

    if response.status_code >= 400:
        raise GoogleAuthError('Google credential could not be verified.')

    data = response.json()
    if data.get('aud') != settings.GOOGLE_CLIENT_ID:
        raise GoogleAuthError('Google credential audience is invalid.')
    if data.get('email_verified') not in [True, 'true', 'True', '1', 1]:
        raise GoogleAuthError('Google account email is not verified.')
    if not data.get('email'):
        raise GoogleAuthError('Google credential does not include an email.')

    return data
