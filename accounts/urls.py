from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView,TokenObtainPairView
from .views import ProfileView, LogoutView
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
]