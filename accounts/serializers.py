from djoser.serializers import UserCreateSerializer
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from .models import CustomUser, SubscriptionPlan, Notification


class CustomUserCreateSerializer(UserCreateSerializer):
    email = serializers.EmailField(required=True)

    class Meta(UserCreateSerializer.Meta):
        model = CustomUser
        fields = ['id', 'username', 'email', 'password']

    def validate_email(self, value):
        # ✅ Prevent duplicate emails on registration
        if CustomUser.objects.filter(email=value).exists():
            raise serializers.ValidationError("This email is already registered.")
        return value


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        user = self.user

        refresh = RefreshToken.for_user(user)
        access = refresh.access_token
        jti = access['jti']

        user.active_token = jti
        user.save()

        data['refresh'] = str(refresh)
        data['access'] = str(access)
        data['is_premium'] = user.is_premium
        return data


class ProfileSerializer(serializers.ModelSerializer):
    current_plan = serializers.StringRelatedField()

    class Meta:
        model = CustomUser
        fields = [
            'id', 'username', 'email', 'phone',
            'profile_picture', 'college', 'semester',
            'bio', 'is_premium', 'premium_expires_at', 'current_plan'
        ]
        read_only_fields = ['is_premium', 'premium_expires_at', 'current_plan']


class ProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['email', 'phone', 'profile_picture', 'college', 'semester', 'bio']

    def validate_email(self, value):
        user = self.instance
        # ✅ Allow same email but block if another user already has it
        if CustomUser.objects.filter(email=value).exclude(id=user.id).exists():
            raise serializers.ValidationError("This email is already in use.")
        return value


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    price_in_rupees = serializers.SerializerMethodField()

    class Meta:
        model = SubscriptionPlan
        fields = ['id', 'name', 'duration', 'price', 'price_in_rupees', 'description']

    def get_price_in_rupees(self, obj):
        return obj.price // 100


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'type', 'message', 'is_read', 'created_at']