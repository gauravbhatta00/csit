from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.generics import ListAPIView
from .models import SubscriptionPlan,Notification
from .serializers import (
    CustomTokenObtainPairSerializer,
    ProfileSerializer,
    ProfileUpdateSerializer,
    SubscriptionPlanSerializer, 
    NotificationSerializer

   
)


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


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
    parser_classes = [MultiPartParser, FormParser]  # ✅ For image upload

    def get(self, request):
        serializer = ProfileSerializer(request.user)
        return Response(serializer.data)

    # ✅ Update profile
    def patch(self, request):
        serializer = ProfileUpdateSerializer(
            request.user,
            data=request.data,
            partial=True
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)


# ✅ List all active subscription plans
class SubscriptionPlanListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        plans = SubscriptionPlan.objects.filter(is_active=True)
        serializer = SubscriptionPlanSerializer(plans, many=True)
        return Response(serializer.data)
    



class NotificationListView(ListAPIView):
    """Get all notifications for logged in user."""
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)


class MarkNotificationReadView(APIView):
    """Mark a specific notification as read."""
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        try:
            notification = Notification.objects.get(
                id=pk,
                user=request.user
            )
            notification.is_read = True
            notification.save()
            return Response({'message': 'Notification marked as read.'})
        except Notification.DoesNotExist:
            return Response({'error': 'Notification not found.'}, status=404)


class MarkAllNotificationsReadView(APIView):
    """Mark all notifications as read."""
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        Notification.objects.filter(
            user=request.user,
            is_read=False
        ).update(is_read=True)
        return Response({'message': 'All notifications marked as read.'})


class UnreadNotificationCountView(APIView):
    """Get unread notification count — for navbar badge."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        count = Notification.objects.filter(
            user=request.user,
            is_read=False
        ).count()
        return Response({'unread_count': count})


class DeleteNotificationView(APIView):
    """Delete a specific notification."""
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        try:
            notification = Notification.objects.get(
                id=pk,
                user=request.user
            )
            notification.delete()
            return Response({'message': 'Notification deleted.'})
        except Notification.DoesNotExist:
            return Response({'error': 'Notification not found.'}, status=404)

