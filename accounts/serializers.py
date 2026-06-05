from djoser.serializers import UserCreateSerializer
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
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
    ContributionSubmission,
    CustomUser,
    DeviceToken,
    EmailCampaign,
    EmailSubscription,
    EmailTemplate,
    Notification,
    Testimonial,
)
from .services import (
    GoogleAuthConfigurationError,
    GoogleAuthError,
    send_activation_email,
    verify_google_id_token,
)


class CustomUserCreateSerializer(UserCreateSerializer):
    class Meta(UserCreateSerializer.Meta):
        model = CustomUser
        fields = ['id', 'username', 'email', 'password']

    def validate_email(self, value):
        value = (value or '').strip().lower()
        if value and CustomUser.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("This email is already registered.")
        return value

    def create(self, validated_data):
        with transaction.atomic():
            user = super().create(validated_data)
            user.is_active = False
            user.account_status = CustomUser.STATUS_ACTIVE
            user.active_token = None
            user.save(update_fields=['is_active', 'account_status', 'active_token'])
            send_activation_email(user)
            return user


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


class ContributionSubmissionSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    reviewed_by_username = serializers.CharField(
        source='reviewed_by.username',
        read_only=True,
    )

    class Meta:
        model = ContributionSubmission
        fields = [
            'id',
            'username',
            'name',
            'email',
            'contribution_type',
            'semester',
            'subject',
            'resource_link',
            'details',
            'status',
            'rejection_reason',
            'reviewed_by_username',
            'reviewed_at',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'username',
            'status',
            'rejection_reason',
            'reviewed_by_username',
            'reviewed_at',
            'created_at',
            'updated_at',
        ]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Name is required.")
        return value

    def validate_email(self, value):
        return value.strip().lower()

    def validate_contribution_type(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Contribution type is required.")
        return value

    def validate_semester(self, value):
        return value.strip()

    def validate_subject(self, value):
        return value.strip()

    def validate_details(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Details are required.")
        return value


class EmailSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailSubscription
        fields = ['id', 'email', 'is_active', 'created_at']
        read_only_fields = ['id', 'is_active', 'created_at']
        extra_kwargs = {'email': {'validators': []}}

    def validate_email(self, value):
        return value.strip().lower()


class EmailTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailTemplate
        fields = [
            'id',
            'slug',
            'name',
            'subject',
            'preheader',
            'body_html',
            'custom_css',
            'is_system',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'is_system', 'created_at', 'updated_at']

    def validate_slug(self, value):
        return value.strip().lower()


class AdminEmailCampaignSerializer(serializers.Serializer):
    recipient_filter = serializers.ChoiceField(
        choices=[
            EmailCampaign.RECIPIENT_ACTIVE_SUBSCRIBERS,
            EmailCampaign.RECIPIENT_ALL_USERS,
        ],
        default=EmailCampaign.RECIPIENT_ACTIVE_SUBSCRIBERS,
    )
    template_id = serializers.IntegerField(required=False)
    template_slug = serializers.CharField(required=False, allow_blank=True)
    subject = serializers.CharField(max_length=180, required=False, allow_blank=True)
    preheader = serializers.CharField(max_length=220, required=False, allow_blank=True)
    body_html = serializers.CharField(required=False, allow_blank=True)
    custom_css = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        template = None
        template_id = attrs.get('template_id')
        template_slug = attrs.get('template_slug')

        if template_id:
            template = EmailTemplate.objects.filter(id=template_id).first()
        elif template_slug:
            template = EmailTemplate.objects.filter(slug=template_slug.strip().lower()).first()

        if (template_id or template_slug) and not template:
            raise serializers.ValidationError({'template_id': 'Template was not found.'})

        subject = (attrs.get('subject') or (template.subject if template else '')).strip()
        body_html = (attrs.get('body_html') or (template.body_html if template else '')).strip()

        if not subject:
            raise serializers.ValidationError({'subject': 'Subject is required.'})
        if not body_html:
            raise serializers.ValidationError({'body_html': 'Email body is required.'})

        attrs['template'] = template
        attrs['subject'] = subject
        attrs['preheader'] = (
            attrs.get('preheader')
            if attrs.get('preheader') is not None
            else (template.preheader if template else '')
        ).strip()
        attrs['body_html'] = body_html
        attrs['custom_css'] = (
            attrs.get('custom_css')
            if attrs.get('custom_css') is not None
            else (template.custom_css if template else '')
        ).strip()
        return attrs


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


class ActivationResendSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        return value.strip().lower()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate_password(self, value):
        validate_password(value)
        return value


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, required=False)
    new_password = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        validate_password(value, self.context["request"].user)
        return value

    def validate(self, attrs):
        user = self.context["request"].user
        if user.has_usable_password():
            current_password = attrs.get("current_password")
            if not current_password or not user.check_password(current_password):
                raise serializers.ValidationError({"current_password": "Current password is incorrect."})
        return attrs


class DeleteAccountSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True, required=False)

    def validate(self, attrs):
        user = self.context["request"].user
        if user.has_usable_password():
            password = attrs.get("password")
            if not password or not user.check_password(password):
                raise serializers.ValidationError({"password": "Password is required and must be correct."})
        return attrs


class DeviceTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceToken
        fields = ["id", "token", "platform", "device_name", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "is_active", "created_at", "updated_at"]

    def validate_token(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Device token is required.")
        return value


class GoogleLoginSerializer(serializers.Serializer):
    credential = serializers.CharField(
        trim_whitespace=True,
        write_only=True,
        error_messages={
            'blank': 'Google credential is required.',
            'required': 'Google credential is required.',
        },
    )

    def validate_credential(self, value):
        if not value:
            raise serializers.ValidationError('Google credential is required.')
        return value

    def validate(self, attrs):
        try:
            attrs['google_user'] = verify_google_id_token(attrs['credential'])
        except GoogleAuthConfigurationError:
            raise
        except GoogleAuthError as exc:
            raise serializers.ValidationError({'credential': str(exc)}) from exc
        return attrs
