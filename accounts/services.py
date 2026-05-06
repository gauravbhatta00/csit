from datetime import timedelta

import requests
from django.conf import settings
from django.db import transaction as db_transaction
from django.utils import timezone

from .models import Notification, PaymentTransaction, UserSubscription


class KhaltiConfigurationError(Exception):
    pass


class KhaltiPaymentError(Exception):
    pass


def _khalti_headers():
    if not settings.KHALTI_SECRET_KEY:
        raise KhaltiConfigurationError('KHALTI_SECRET_KEY is not configured.')

    return {
        'Authorization': f'Key {settings.KHALTI_SECRET_KEY}',
        'Content-Type': 'application/json',
    }


def _khalti_url(path):
    return f"{settings.KHALTI_API_BASE_URL.rstrip('/')}/{path.lstrip('/')}"


def initiate_khalti_payment(payment):
    payload = {
        'return_url': f"{settings.FRONTEND_BASE_URL.rstrip('/')}/payment/khalti/return",
        'website_url': settings.FRONTEND_BASE_URL.rstrip('/'),
        'amount': payment.amount_paisa,
        'purchase_order_id': payment.purchase_order_id,
        'purchase_order_name': payment.purchase_order_name,
        'customer_info': {
            'name': payment.customer_name,
            'email': payment.customer_email,
            'phone': payment.customer_phone,
        },
        'amount_breakdown': [
            {
                'label': payment.plan.name,
                'amount': payment.amount_paisa,
            }
        ],
        'product_details': [
            {
                'identity': payment.plan.slug,
                'name': payment.plan.name,
                'total_price': payment.amount_paisa,
                'quantity': 1,
                'unit_price': payment.amount_paisa,
            }
        ],
    }

    response = requests.post(
        _khalti_url('/epayment/initiate/'),
        json=payload,
        headers=_khalti_headers(),
        timeout=20,
    )

    if response.status_code >= 400:
        raise KhaltiPaymentError(response.text)

    data = response.json()
    payment.pidx = data.get('pidx')
    payment.payment_url = data.get('payment_url', '')
    payment.raw_initiate_response = data
    payment.save(
        update_fields=[
            'pidx',
            'payment_url',
            'raw_initiate_response',
            'updated_at',
        ]
    )
    return data


def lookup_khalti_payment(pidx):
    response = requests.post(
        _khalti_url('/epayment/lookup/'),
        json={'pidx': pidx},
        headers=_khalti_headers(),
        timeout=20,
    )

    if response.status_code >= 400:
        raise KhaltiPaymentError(response.text)

    return response.json()


def map_khalti_status(status):
    normalized = (status or '').strip().lower()

    if normalized == 'completed':
        return PaymentTransaction.STATUS_COMPLETED
    if normalized == 'pending':
        return PaymentTransaction.STATUS_PENDING
    if normalized == 'expired':
        return PaymentTransaction.STATUS_EXPIRED
    if normalized == 'refunded' or normalized == 'partially refunded':
        return PaymentTransaction.STATUS_REFUNDED
    if normalized == 'user canceled':
        return PaymentTransaction.STATUS_CANCELED
    if normalized == 'initiated':
        return PaymentTransaction.STATUS_INITIATED
    return PaymentTransaction.STATUS_FAILED


@db_transaction.atomic
def apply_khalti_lookup(payment, lookup_data):
    payment.raw_lookup_response = lookup_data
    payment.status = map_khalti_status(lookup_data.get('status'))
    payment.khalti_transaction_id = lookup_data.get('transaction_id') or ''

    if payment.status == PaymentTransaction.STATUS_COMPLETED:
        payment.completed_at = timezone.now()
        payment.subscription = activate_subscription(payment)

    payment.save(
        update_fields=[
            'raw_lookup_response',
            'status',
            'khalti_transaction_id',
            'completed_at',
            'subscription',
            'updated_at',
        ]
    )
    return payment


def activate_subscription(payment):
    if payment.subscription_id:
        return payment.subscription

    starts_at = timezone.now()
    expires_at = starts_at + timedelta(days=payment.plan.duration_days)
    subscription = UserSubscription.objects.create(
        user=payment.user,
        plan=payment.plan,
        starts_at=starts_at,
        expires_at=expires_at,
        is_active=True,
    )
    user = payment.user
    user.is_premium = True
    user.premium_expires_at = expires_at
    user.current_plan = payment.plan
    user.save(update_fields=['is_premium', 'premium_expires_at', 'current_plan'])
    Notification.objects.create(
        user=user,
        type=Notification.TYPE_PAYMENT,
        message=f"{payment.plan.name} subscription activated.",
    )
    return subscription
