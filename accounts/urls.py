from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView,TokenObtainPairView
from .views import (
    DeleteNotificationView,
    KhaltiInitiateView,
    KhaltiVerifyView,
    LogoutView,
    MarkAllNotificationsReadView,
    MarkNotificationReadView,
    MySubscriptionListView,
    NotificationListView,
    ProfileView,
    SubscriptionPlanDetailView,
    SubscriptionPlanListView,
    UnreadNotificationCountView,
)
from .serializers import CustomTokenObtainPairSerializer


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer  # ✅ Must point to custom serializer


urlpatterns = [
    path('', include('djoser.urls')),
    path('jwt/create/', CustomTokenObtainPairView.as_view()),  # ✅ Custom view
    path('jwt/refresh/', TokenRefreshView.as_view()),
    path('jwt/verify/', TokenVerifyView.as_view()),
    path('logout/', LogoutView.as_view()),
    path('profile/', ProfileView.as_view()),
    path('subscription-plans/', SubscriptionPlanListView.as_view()),
    path('subscription-plans/<slug:slug>/', SubscriptionPlanDetailView.as_view()),
    path('my-subscriptions/', MySubscriptionListView.as_view()),
    path('payments/khalti/initiate/', KhaltiInitiateView.as_view()),
    path('payments/khalti/verify/', KhaltiVerifyView.as_view()),
    path('notifications/', NotificationListView.as_view()),
    path('notifications/unread-count/', UnreadNotificationCountView.as_view()),
    path('notifications/mark-all-read/', MarkAllNotificationsReadView.as_view()),
    path('notifications/<int:pk>/read/', MarkNotificationReadView.as_view()),
    path('notifications/<int:pk>/', DeleteNotificationView.as_view()),
]
