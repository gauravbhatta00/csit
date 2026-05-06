from rest_framework.views import APIView
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from django.utils.crypto import get_random_string
from .models import (
    Notification,
    PaymentTransaction,
    SubscriptionPlan,
    UserSubscription,
)
from .serializers import (
    KhaltiInitiateSerializer,
    KhaltiVerifySerializer,
    NotificationSerializer,
    PaymentTransactionSerializer,
    ProfileSerializer,
    ProfileUpdateSerializer,
    SubscriptionPlanSerializer,
    UserSubscriptionSerializer,
)
from .services import (
    KhaltiConfigurationError,
    KhaltiPaymentError,
    apply_khalti_lookup,
    initiate_khalti_payment,
    lookup_khalti_payment,
)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response({'error': 'Refresh token is required.'}, status=400)
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            request.user.active_token = None
            request.user.save()
            return Response({'message': 'Logged out successfully.'})
        except TokenError:
            return Response({'error': 'Invalid or expired token.'}, status=400)


class ProfileView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        serializer = ProfileSerializer(request.user)
        return Response(serializer.data)

    def patch(self, request):
        serializer = ProfileUpdateSerializer(
            request.user,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(ProfileSerializer(request.user).data)


class SubscriptionPlanListView(ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = SubscriptionPlanSerializer

    def get_queryset(self):
        return SubscriptionPlan.objects.filter(is_active=True)


class SubscriptionPlanDetailView(RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = SubscriptionPlanSerializer
    lookup_field = 'slug'

    def get_queryset(self):
        return SubscriptionPlan.objects.filter(is_active=True)


class MySubscriptionListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserSubscriptionSerializer

    def get_queryset(self):
        return UserSubscription.objects.filter(
            user=self.request.user,
        ).select_related('plan')


class KhaltiInitiateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = KhaltiInitiateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            plan = SubscriptionPlan.objects.get(
                slug=data['plan_slug'],
                is_active=True,
            )
        except SubscriptionPlan.DoesNotExist:
            return Response(
                {'detail': 'Selected subscription plan was not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        amount_paisa = int(plan.price * 100)
        purchase_order_id = f"sub-{request.user.id}-{get_random_string(12)}"
        payment = PaymentTransaction.objects.create(
            user=request.user,
            plan=plan,
            amount=plan.price,
            amount_paisa=amount_paisa,
            purchase_order_id=purchase_order_id,
            purchase_order_name=f"{plan.name} subscription",
            customer_name=data['customer_name'],
            customer_email=data.get('customer_email', ''),
            customer_phone=data.get('customer_phone', ''),
        )

        try:
            initiate_khalti_payment(payment)
        except KhaltiConfigurationError as exc:
            payment.status = PaymentTransaction.STATUS_FAILED
            payment.save(update_fields=['status', 'updated_at'])
            return Response(
                {'detail': str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except KhaltiPaymentError as exc:
            payment.status = PaymentTransaction.STATUS_FAILED
            payment.save(update_fields=['status', 'updated_at'])
            return Response(
                {'detail': 'Khalti initiation failed.', 'error': str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(PaymentTransactionSerializer(payment).data)


class KhaltiVerifyView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = KhaltiVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pidx = serializer.validated_data['pidx']

        try:
            payment = PaymentTransaction.objects.select_related(
                'plan',
                'user',
                'subscription',
            ).get(pidx=pidx, user=request.user)
        except PaymentTransaction.DoesNotExist:
            return Response(
                {'detail': 'Payment transaction was not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            lookup_data = lookup_khalti_payment(pidx)
        except KhaltiConfigurationError as exc:
            return Response(
                {'detail': str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except KhaltiPaymentError as exc:
            return Response(
                {'detail': 'Khalti lookup failed.', 'error': str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        payment = apply_khalti_lookup(payment, lookup_data)
        return Response(PaymentTransactionSerializer(payment).data)


class NotificationListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)


class MarkNotificationReadView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        try:
            notification = Notification.objects.get(id=pk, user=request.user)
        except Notification.DoesNotExist:
            return Response(
                {'detail': 'Notification not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        notification.is_read = True
        notification.save(update_fields=['is_read'])
        return Response(NotificationSerializer(notification).data)


class MarkAllNotificationsReadView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        Notification.objects.filter(
            user=request.user,
            is_read=False,
        ).update(is_read=True)
        return Response({'message': 'All notifications marked as read.'})


class UnreadNotificationCountView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        count = Notification.objects.filter(
            user=request.user,
            is_read=False,
        ).count()
        return Response({'unread_count': count})


class DeleteNotificationView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        try:
            notification = Notification.objects.get(id=pk, user=request.user)
        except Notification.DoesNotExist:
            return Response(
                {'detail': 'Notification not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        notification.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
