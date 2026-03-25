from djoser.serializers import UserCreateSerializer
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from .models import CustomUser


class CustomUserCreateSerializer(UserCreateSerializer):
    class Meta(UserCreateSerializer.Meta):
        model = CustomUser
        fields = ['id', 'username', 'email', 'password']


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):

    def validate(self, attrs):
        data = super().validate(attrs)
        user = self.user

        refresh = RefreshToken.for_user(user)
        access = refresh.access_token

        # ✅ Save ACCESS token jti — because request.auth is the access token
        jti = access['jti']
        user.active_token = jti
        user.save()

        data['refresh'] = str(refresh)
        data['access'] = str(access)
        data['is_premium'] = user.is_premium

        return data