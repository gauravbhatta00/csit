from djoser.serializers import UserCreateSerializer
from rest_framework import serializers
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
    PaymentTransaction,
    SubscriptionPlan,
    UserSubscription,
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


class CustomTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        refresh = RefreshToken(attrs['refresh'])
        user_id = refresh[api_settings.USER_ID_CLAIM]
        data = super().validate(attrs)
        access = AccessToken(data['access'])

        CustomUser.objects.filter(id=user_id).update(active_token=access['jti'])
        return data


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = [
            'id',
            'name',
            'slug',
            'price',
            'billing_period',
            'duration_days',
            'description',
            'features',
            'is_active',
        ]


class UserSubscriptionSerializer(serializers.ModelSerializer):
    plan = SubscriptionPlanSerializer(read_only=True)

    class Meta:
        model = UserSubscription
        fields = [
            'id',
            'plan',
            'starts_at',
            'expires_at',
            'is_active',
        ]


class ProfileSerializer(serializers.ModelSerializer):
    current_plan = SubscriptionPlanSerializer(read_only=True)

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
            'is_premium',
            'premium_expires_at',
            'current_plan',
        ]
        read_only_fields = [
            'id',
            'username',
            'is_staff',
            'is_premium',
            'premium_expires_at',
            'current_plan',
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


class KhaltiInitiateSerializer(serializers.Serializer):
    plan_slug = serializers.SlugField()
    customer_name = serializers.CharField(max_length=150)
    customer_email = serializers.EmailField(required=False, allow_blank=True)
    customer_phone = serializers.CharField(
        max_length=30,
        required=False,
        allow_blank=True,
    )


class KhaltiVerifySerializer(serializers.Serializer):
    pidx = serializers.CharField(max_length=100)


class PaymentTransactionSerializer(serializers.ModelSerializer):
    plan = SubscriptionPlanSerializer(read_only=True)

    class Meta:
        model = PaymentTransaction
        fields = [
            'id',
            'plan',
            'payment_method',
            'amount',
            'amount_paisa',
            'status',
            'pidx',
            'payment_url',
            'khalti_transaction_id',
            'purchase_order_id',
            'purchase_order_name',
            'customer_name',
            'customer_email',
            'customer_phone',
            'created_at',
            'updated_at',
            'completed_at',
        ]


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
