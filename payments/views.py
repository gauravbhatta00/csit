import requests
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import Payment
from accounts.models import SubscriptionPlan
from academics.utils import notify_payment


DURATION_DAYS = {
    'monthly': 30,
    'quarterly': 90,
    'yearly': 365,
}


class InitiatePaymentView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        plan_id = request.data.get('plan_id')  # ✅ Frontend sends plan_id

        if not plan_id:
            return Response({'error': 'plan_id is required.'}, status=400)

        try:
            plan = SubscriptionPlan.objects.get(id=plan_id, is_active=True)
        except SubscriptionPlan.DoesNotExist:
            return Response({'error': 'Invalid plan.'}, status=404)

        payment = Payment.objects.create(
            user=request.user,
            amount=plan.price,
            status='pending',
            plan=plan  # ✅ Save plan with payment
        )

        headers = {
            'Authorization': f'key {settings.KHALTI_SECRET_KEY}',
            'Content-Type': 'application/json',
        }

        payload = {
            'return_url': 'http://localhost:5173/payment/verify',
            'website_url': 'http://localhost:5173',
            'amount': plan.price,
            'purchase_order_id': str(payment.id),
            'purchase_order_name': plan.name,
            'customer_info': {
                'name': request.user.username,
                'email': request.user.email,
            }
        }

        response = requests.post(
            settings.KHALTI_INITIATE_URL,
            json=payload,
            headers=headers
        )

        if response.status_code == 200:
            data = response.json()
            payment.pidx = data['pidx']
            payment.save()
            return Response({
                'payment_url': data['payment_url'],
                'pidx': data['pidx'],
            })
        else:
            payment.status = 'failed'
            payment.save()
            return Response({'error': 'Payment initiation failed.'}, status=400)


class VerifyPaymentView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        pidx = request.query_params.get('pidx')
        if not pidx:
            return Response({'error': 'pidx is required.'}, status=400)

        headers = {
            'Authorization': f'key {settings.KHALTI_SECRET_KEY}',
            'Content-Type': 'application/json',
        }

        response = requests.post(
            settings.KHALTI_LOOKUP_URL,
            json={'pidx': pidx},
            headers=headers
        )

        if response.status_code != 200:
            return Response({'error': 'Verification failed.'}, status=400)

        data = response.json()

        try:
            payment = Payment.objects.get(pidx=pidx)
        except Payment.DoesNotExist:
            return Response({'error': 'Payment not found.'}, status=404)

        if data.get('status') == 'Completed':
            payment.status = 'completed'
            payment.transaction_id = data.get('transaction_id')
            payment.save()

            # ✅ Activate premium based on plan duration
            user = payment.user
            plan = payment.plan
            days = DURATION_DAYS.get(plan.duration, 30)

            user.is_premium = True
            user.premium_expires_at = timezone.now() + timedelta(days=days)
            user.current_plan = plan
            user.save()

            return Response({
                'message': f'Payment successful. {plan.name} activated!',
                'plan': plan.name,
                'expires_at': user.premium_expires_at,
            })

        return Response({'message': f'Payment status: {data.get("status")}'}, status=400)
    



class VerifyPaymentView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        pidx = request.query_params.get('pidx')
        if not pidx:
            return Response({'error': 'pidx is required.'}, status=400)

        headers = {
            'Authorization': f'key {settings.KHALTI_SECRET_KEY}',
            'Content-Type': 'application/json',
        }

        response = requests.post(
            settings.KHALTI_LOOKUP_URL,
            json={'pidx': pidx},
            headers=headers
        )

        if response.status_code != 200:
            return Response({'error': 'Verification failed.'}, status=400)

        data = response.json()

        try:
            payment = Payment.objects.get(pidx=pidx)
        except Payment.DoesNotExist:
            return Response({'error': 'Payment not found.'}, status=404)

        if data.get('status') == 'Completed':
            payment.status = 'completed'
            payment.transaction_id = data.get('transaction_id')
            payment.save()

            user = payment.user
            plan = payment.plan
            days = DURATION_DAYS.get(plan.duration, 30)

            user.is_premium = True
            user.premium_expires_at = timezone.now() + timedelta(days=days)
            user.current_plan = plan
            user.save()

            # ✅ Send payment notification
            notify_payment(
                user=user,
                plan_name=plan.name,
                amount=plan.price
            )

            return Response({
                'message': f'Payment successful. {plan.name} activated!',
                'plan': plan.name,
                'expires_at': user.premium_expires_at,
            })

        return Response({'message': f'Payment status: {data.get("status")}'}, status=400)