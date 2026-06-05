import logging
import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.html import strip_tags
from django.utils.http import urlsafe_base64_encode
from google.auth.exceptions import GoogleAuthError as GoogleLibraryAuthError
from google.auth.transport.requests import Request
from google.oauth2 import id_token
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import RefreshToken

from .models import EmailSubscription, EmailTemplate


logger = logging.getLogger(__name__)


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


DEFAULT_EMAIL_TEMPLATES = [
    {
        'slug': 'study-update',
        'name': 'Study update',
        'subject': 'New CSIT resources are ready',
        'preheader': 'Fresh notes, questions, and updates from Ramro CSIT.',
        'body_html': (
            '<h2>Fresh CSIT resources are ready</h2>'
            '<p>We have added new study resources to help you revise faster.</p>'
            '<p><a class="button" href="{{ frontend_url }}">Browse resources</a></p>'
        ),
        'custom_css': '',
    },
    {
        'slug': 'exam-reminder',
        'name': 'Exam reminder',
        'subject': 'Plan your next CSIT revision session',
        'preheader': 'A focused reminder for upcoming CSIT preparation.',
        'body_html': (
            '<h2>Keep your revision moving</h2>'
            '<p>Use recent questions, syllabus units, and notes to plan your next session.</p>'
            '<p><a class="button" href="{{ frontend_url }}/semester">Open semesters</a></p>'
        ),
        'custom_css': '',
    },
    {
        'slug': 'custom-announcement',
        'name': 'Custom announcement',
        'subject': 'A quick update from Ramro CSIT',
        'preheader': 'A short update for CSIT students.',
        'body_html': (
            '<h2>Ramro CSIT update</h2>'
            '<p>Write your announcement here.</p>'
            '<p><a class="button" href="{{ frontend_url }}">Visit Ramro CSIT</a></p>'
        ),
        'custom_css': '',
    },
]


def normalize_email(email):
    return (email or '').strip().lower()


def ensure_default_email_templates():
    for template in DEFAULT_EMAIL_TEMPLATES:
        EmailTemplate.objects.update_or_create(
            slug=template['slug'],
            defaults={**template, 'is_system': True},
        )


def subscribe_email(email, source='manual'):
    email = normalize_email(email)
    if not email:
        return None
    subscription = EmailSubscription.objects.filter(email__iexact=email).first()
    if subscription:
        subscription.email = email
        subscription.is_active = True
        subscription.source = source
        subscription.save(update_fields=['email', 'is_active', 'source', 'updated_at'])
        return subscription

    subscription = EmailSubscription.objects.create(
        email=email,
        is_active=True,
        source=source,
    )
    return subscription


def build_frontend_url(path='', query=''):
    base_url = settings.FRONTEND_BASE_URL.rstrip('/')
    normalized_path = f"/{path.lstrip('/')}" if path else ''
    return f"{base_url}{normalized_path}{query}"


def build_unsubscribe_url(subscription):
    return build_frontend_url(
        '/unsubscribe',
        f'?token={subscription.unsubscribe_token}',
    )


def render_email_html(title, preheader, body_html, custom_css='', unsubscribe_url=''):
    context = {
        'title': title,
        'preheader': preheader,
        'body_html': body_html,
        'custom_css': custom_css,
        'unsubscribe_url': unsubscribe_url,
        'frontend_url': settings.FRONTEND_BASE_URL.rstrip('/'),
        'brand_name': getattr(settings, 'EMAIL_BRAND_NAME', 'Ramro CSIT'),
        'logo_url': getattr(settings, 'EMAIL_LOGO_URL', ''),
    }
    return render_to_string('accounts/email/base.html', context)


def render_template_placeholders(value, subscription=None):
    frontend_url = settings.FRONTEND_BASE_URL.rstrip('/')
    replacements = {
        '{{ frontend_url }}': frontend_url,
        '{{ unsubscribe_url }}': build_unsubscribe_url(subscription) if subscription else '',
    }
    rendered = value or ''
    for key, replacement in replacements.items():
        rendered = rendered.replace(key, replacement)
    return rendered


def send_html_email(subject, body_html, recipients, preheader='', custom_css='', unsubscribe_url=''):
    html_body = render_email_html(
        title=subject,
        preheader=preheader,
        body_html=body_html,
        custom_css=custom_css,
        unsubscribe_url=unsubscribe_url,
    )
    text_body = strip_tags(
        re.sub(r'</(p|h1|h2|h3|li|div)>', '\n', html_body, flags=re.IGNORECASE)
    )
    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=recipients,
    )
    message.attach_alternative(html_body, 'text/html')
    message.send(fail_silently=False)


def send_activation_email(user):
    subscription = subscribe_email(user.email, source='signup')
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    activation_url = build_frontend_url(
        '/activate-account',
        f'?uid={uid}&token={token}',
    )
    body_html = (
        '<h2>Activate your Ramro CSIT account</h2>'
        '<p>Welcome to Ramro CSIT. Confirm your email to finish setting up your account '
        'and start saving your CSIT study progress.</p>'
        f'<p><a class="button" href="{activation_url}">Activate account</a></p>'
        '<p class="muted">This link is private. If you did not create a Ramro CSIT account, '
        'you can safely ignore this email.</p>'
    )
    try:
        send_html_email(
            subject='Activate your Ramro CSIT account',
            preheader='Confirm your email to finish creating your account.',
            body_html=body_html,
            recipients=[user.email],
            unsubscribe_url=build_unsubscribe_url(subscription) if subscription else '',
        )
    except Exception:
        logger.exception('Failed to send activation email to user_id=%s', user.id)
        raise


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
