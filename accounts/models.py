from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.utils import timezone
from django.utils.text import slugify


class CustomUserManager(BaseUserManager):
    """Handles user creation with email and username."""

    def create_user(self, username, email=None, password=None, **extra_fields):
        if not username:
            raise ValueError('Username is required.')
        email = self.normalize_email(email)
        extra_fields.setdefault('is_premium', False)
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_premium', True)  # ✅ Superuser gets premium

        if not extra_fields.get('is_staff'):
            raise ValueError('Superuser must have is_staff=True.')
        if not extra_fields.get('is_superuser'):
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(username, email, password, **extra_fields)


class CustomUser(AbstractUser):
    # ✅ Premium fields directly on user model
    phone = models.CharField(max_length=15, null=True, blank=True)
    profile_picture = models.ImageField(upload_to='profiles/', null=True, blank=True)
    college = models.CharField(max_length=100, null=True, blank=True)
    semester = models.CharField(max_length=20, null=True, blank=True)
    bio = models.TextField(null=True, blank=True)
    is_premium = models.BooleanField(default=False)
    premium_expires_at = models.DateTimeField(null=True, blank=True)
    active_token = models.CharField(max_length=255, null=True, blank=True)
    current_plan = models.ForeignKey(
        'SubscriptionPlan',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='subscribers',
    )

    objects = CustomUserManager()  # ✅ Use our custom manager

    def is_premium_active(self):
        """Check if premium is active and not expired."""
        if not self.is_premium:
            return False
        if self.premium_expires_at and self.premium_expires_at < timezone.now():
            self.is_premium = False
            self.save()
            return False
        return True

    def __str__(self):
        return f"{self.username} - {'Premium' if self.is_premium else 'Free'}"


class SubscriptionPlan(models.Model):
    BILLING_MONTHLY = 'monthly'
    BILLING_QUARTERLY = 'quarterly'
    BILLING_YEARLY = 'yearly'
    BILLING_CUSTOM = 'custom'

    BILLING_PERIOD_CHOICES = [
        (BILLING_MONTHLY, 'Monthly'),
        (BILLING_QUARTERLY, 'Quarterly'),
        (BILLING_YEARLY, 'Yearly'),
        (BILLING_CUSTOM, 'Custom'),
    ]

    name = models.CharField(max_length=80)
    slug = models.SlugField(unique=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    billing_period = models.CharField(
        max_length=20,
        choices=BILLING_PERIOD_CHOICES,
        default=BILLING_MONTHLY,
    )
    duration_days = models.PositiveIntegerField(default=30)
    description = models.TextField(blank=True)
    features = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'price']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} - Rs. {self.price}"


class UserSubscription(models.Model):
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='subscriptions',
    )
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.PROTECT,
        related_name='subscriptions',
    )
    starts_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-starts_at']

    def __str__(self):
        return f"{self.user.username} - {self.plan.name}"


class PaymentTransaction(models.Model):
    STATUS_INITIATED = 'initiated'
    STATUS_PENDING = 'pending'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'
    STATUS_CANCELED = 'canceled'
    STATUS_EXPIRED = 'expired'
    STATUS_REFUNDED = 'refunded'

    STATUS_CHOICES = [
        (STATUS_INITIATED, 'Initiated'),
        (STATUS_PENDING, 'Pending'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_CANCELED, 'Canceled'),
        (STATUS_EXPIRED, 'Expired'),
        (STATUS_REFUNDED, 'Refunded'),
    ]

    PAYMENT_METHOD_KHALTI = 'khalti'

    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='payment_transactions',
    )
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.PROTECT,
        related_name='payment_transactions',
    )
    subscription = models.ForeignKey(
        UserSubscription,
        on_delete=models.SET_NULL,
        related_name='payment_transactions',
        null=True,
        blank=True,
    )
    payment_method = models.CharField(max_length=30, default=PAYMENT_METHOD_KHALTI)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    amount_paisa = models.PositiveIntegerField()
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_INITIATED,
    )
    pidx = models.CharField(max_length=100, unique=True, null=True, blank=True)
    payment_url = models.URLField(max_length=500, blank=True)
    khalti_transaction_id = models.CharField(max_length=100, blank=True)
    purchase_order_id = models.CharField(max_length=80, unique=True)
    purchase_order_name = models.CharField(max_length=160)
    customer_name = models.CharField(max_length=150)
    customer_email = models.EmailField(blank=True)
    customer_phone = models.CharField(max_length=30, blank=True)
    raw_initiate_response = models.JSONField(default=dict, blank=True)
    raw_lookup_response = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.plan.name} - {self.status}"


class ContactMessage(models.Model):
    name = models.CharField(max_length=120)
    email = models.EmailField()
    message = models.TextField()
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} - {self.email}"


class EmailSubscription(models.Model):
    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.email


class Notification(models.Model):
    TYPE_GENERAL = 'general'
    TYPE_REPLY = 'reply'
    TYPE_PAPER = 'paper'
    TYPE_MOCK_TEST = 'mock_test'
    TYPE_PREMIUM_EXPIRY = 'premium_expiry'
    TYPE_PAYMENT = 'payment'

    TYPE_CHOICES = [
        (TYPE_GENERAL, 'General'),
        (TYPE_REPLY, 'Discussion Reply'),
        (TYPE_PAPER, 'New Question Paper'),
        (TYPE_MOCK_TEST, 'New Mock Test'),
        (TYPE_PREMIUM_EXPIRY, 'Premium Expiring'),
        (TYPE_PAYMENT, 'Payment'),
    ]

    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    message = models.TextField()
    link_path = models.CharField(max_length=255, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.type} - {self.message[:50]}"
