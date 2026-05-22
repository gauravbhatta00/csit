from djoser.serializers import UserCreateSerializer
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import (
    TokenObtainPairSerializer,
    TokenRefreshSerializer,
)
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from .models import (
    ContactMessage,
    CustomUser,
    EmailSubscription,
    Notification,
    Testimonial,
)


class CustomUserCreateSerializer(UserCreateSerializer):
    class Meta(UserCreateSerializer.Meta):
        model = CustomUser
        fields = ['id', 'username', 'email', 'password']

    def validate_email(self, value):
        if value and CustomUser.objects.filter(email=value).exists():
            raise serializers.ValidationError("This email is already registered.")
        return value


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):

    def validate(self, attrs):
        username = attrs.get(self.username_field)
        if username:
            user = CustomUser.objects.filter(**{self.username_field: username}).first()
            if user:
                user.refresh_expired_suspension(save=True)
                if not user.is_active:
                    raise AuthenticationFailed(user.account_unavailable_message())

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
        return data


class CustomTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        refresh = RefreshToken(attrs['refresh'])
        user_id = refresh[api_settings.USER_ID_CLAIM]
        try:
            user = CustomUser.objects.get(id=user_id)
        except CustomUser.DoesNotExist as exc:
            raise AuthenticationFailed(
                'Your account is not active. For more info, contact support.'
            ) from exc
        user.refresh_expired_suspension(save=True)
        if not user.is_active:
            raise AuthenticationFailed(user.account_unavailable_message())

        data = super().validate(attrs)
        access = AccessToken(data['access'])

        CustomUser.objects.filter(id=user_id).update(active_token=access['jti'])
        return data


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = [
            'id',
            'username',
            'email',
            'phone',
            'profile_picture',
            'college',
            'semester',
            'bio',
            'is_staff',
        ]
        read_only_fields = [
            'id',
            'username',
            'is_staff',
        ]


class ProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['email', 'phone', 'profile_picture', 'college', 'semester', 'bio']

    def validate_email(self, value):
        user = self.instance
        if value and CustomUser.objects.filter(email=value).exclude(id=user.id).exists():
            raise serializers.ValidationError("This email is already in use.")
        return value


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'type', 'message', 'link_path', 'is_read', 'created_at']


class ContactMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactMessage
        fields = ['id', 'name', 'email', 'message', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Name is required.")
        return value

    def validate_message(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Message is required.")
        return value


class EmailSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailSubscription
        fields = ['id', 'email', 'is_active', 'created_at']
        read_only_fields = ['id', 'is_active', 'created_at']
        extra_kwargs = {'email': {'validators': []}}

    def validate_email(self, value):
        return value.strip().lower()


class TestimonialSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    reviewed_by_username = serializers.CharField(
        source='reviewed_by.username',
        read_only=True,
    )

    class Meta:
        model = Testimonial
        fields = [
            'id',
            'name',
            'role',
            'rating',
            'review',
            'status',
            'username',
            'reviewed_by_username',
            'reviewed_at',
            'created_at',
        ]
        read_only_fields = [
            'id',
            'status',
            'username',
            'reviewed_by_username',
            'reviewed_at',
            'created_at',
        ]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Name is required.")
        return value

    def validate_role(self, value):
        return value.strip()

    def validate_rating(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError("Rating must be between 1 and 5.")
        return value

    def validate_review(self, value):
        value = value.strip()
        if len(value) < 12:
            raise serializers.ValidationError(
                "Review must be at least 12 characters.",
            )
        return value


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        return value.strip().lower()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(min_length=8, write_only=True)


class GoogleLoginSerializer(serializers.Serializer):
    credential = serializers.CharField()
