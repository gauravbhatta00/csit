
from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.utils import timezone


class CustomUserManager(BaseUserManager):
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
        extra_fields.setdefault('is_premium', True)
        return self.create_user(username, email, password, **extra_fields)


class CustomUser(AbstractUser):
    email = models.EmailField(unique=True)          # ✅ THIS LINE IS CRITICAL
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
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='subscribers'
    )

    objects = CustomUserManager()

    def is_premium_active(self):
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
    DURATION_CHOICES = [
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
    ]
    name = models.CharField(max_length=50)
    duration = models.CharField(max_length=20, choices=DURATION_CHOICES)
    price = models.PositiveIntegerField()
    description = models.TextField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def price_in_rupees(self):
        return self.price // 100

    def __str__(self):
        return f"{self.name} - Rs.{self.price_in_rupees()} ({self.duration})"
    
class Notification(models.Model):
    TYPE_CHOICES = [
        ('reply', 'Discussion Reply'),
        ('paper', 'New Question Paper'),
        ('mock_test', 'New Mock Test'),
        ('premium_expiry', 'Premium Expiring'),
        ('payment', 'Payment'),
    ]

    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.type} - {self.message[:50]}"