from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView
from .views import (
    CustomTokenObtainPairView,
    LogoutView,
    ProfileView,
    SubscriptionPlanListView,
    NotificationListView,           # ✅ ADD
    MarkNotificationReadView,       # ✅ ADD
    MarkAllNotificationsReadView,   # ✅ ADD
    UnreadNotificationCountView,    # ✅ ADD
    DeleteNotificationView, 
)

urlpatterns = [
    path('', include('djoser.urls')),       # ✅ Djoser auto adds all these:
                                            # /users/                    → register
                                            # /users/activation/         → activate email
                                            # /users/reset_password/     → forgot password
                                            # /users/reset_password_confirm/ → reset password
    path('jwt/create/', CustomTokenObtainPairView.as_view()),
    path('jwt/refresh/', TokenRefreshView.as_view()),
    path('jwt/verify/', TokenVerifyView.as_view()),
    path('logout/', LogoutView.as_view()),
    path('profile/', ProfileView.as_view()),
    path('plans/', SubscriptionPlanListView.as_view()),
    path('notifications/', NotificationListView.as_view()),
    path('notifications/unread-count/', UnreadNotificationCountView.as_view()),
    path('notifications/mark-all-read/', MarkAllNotificationsReadView.as_view()),
    path('notifications/<int:pk>/read/', MarkNotificationReadView.as_view()),
    path('notifications/<int:pk>/delete/', DeleteNotificationView.as_view()),
    
    
]