import math

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone


class CustomUserManager(BaseUserManager):
    """Handles user creation with email and username."""

    def create_user(self, username, email=None, password=None, **extra_fields):
        if not username:
            raise ValueError('Username is required.')
        email = self.normalize_email(email)
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if not extra_fields.get('is_staff'):
            raise ValueError('Superuser must have is_staff=True.')
        if not extra_fields.get('is_superuser'):
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(username, email, password, **extra_fields)


class CustomUser(AbstractUser):
    STATUS_ACTIVE = 'active'
    STATUS_SUSPENDED = 'suspended'
    STATUS_BLOCKED = 'blocked'

    ACCOUNT_STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_SUSPENDED, 'Suspended'),
        (STATUS_BLOCKED, 'Blocked'),
    ]

    phone = models.CharField(max_length=15, null=True, blank=True)
    profile_picture = models.ImageField(upload_to='profiles/', null=True, blank=True)
    college = models.CharField(max_length=100, null=True, blank=True)
    semester = models.CharField(max_length=20, null=True, blank=True)
    bio = models.TextField(null=True, blank=True)
    active_token = models.CharField(max_length=255, null=True, blank=True)
    suspended_until = models.DateTimeField(null=True, blank=True)
    account_status = models.CharField(
        max_length=20,
        choices=ACCOUNT_STATUS_CHOICES,
        default=STATUS_ACTIVE,
    )

    objects = CustomUserManager()

    def refresh_expired_suspension(self, save=False):
        if (
            self.account_status == self.STATUS_SUSPENDED
            and self.suspended_until
            and self.suspended_until <= timezone.now()
        ):
            self.account_status = self.STATUS_ACTIVE
            self.is_active = True
            self.suspended_until = None
            if save:
                self.save(update_fields=['account_status', 'is_active', 'suspended_until'])
            return True
        return False

    def suspension_days_remaining(self):
        if not self.suspended_until:
            return None

        seconds = max(
            0,
            (self.suspended_until - timezone.now()).total_seconds(),
        )
        return max(1, math.ceil(seconds / 86400))

    def account_unavailable_message(self):
        if self.account_status == self.STATUS_SUSPENDED:
            days = self.suspension_days_remaining()
            if days:
                unit = 'day' if days == 1 else 'days'
                return (
                    f"Your account is suspended for {days} more {unit}. "
                    "For more info, contact support."
                )
            return "Your account is suspended. For more info, contact support."

        if self.account_status == self.STATUS_BLOCKED:
            return "Your account is blocked. For more info, contact support."

        return "Your account is not active. For more info, contact support."

    def set_account_status(self, account_status, suspended_until=None):
        self.account_status = account_status
        self.is_active = account_status == self.STATUS_ACTIVE
        self.suspended_until = (
            suspended_until if account_status == self.STATUS_SUSPENDED else None
        )
        if not self.is_active:
            self.active_token = None

    def __str__(self):
        return self.username


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


class Testimonial(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
    ]

    user = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        related_name='testimonials',
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=120)
    role = models.CharField(max_length=120, blank=True)
    rating = models.PositiveSmallIntegerField(default=5)
    review = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )
    reviewed_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        related_name='reviewed_testimonials',
        null=True,
        blank=True,
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user'],
                condition=models.Q(user__isnull=False),
                name='unique_testimonial_per_user',
            ),
        ]

    def __str__(self):
        return f"{self.name} - {self.rating}/5 - {self.status}"


class Notification(models.Model):
    TYPE_REPLY = 'reply'
    TYPE_PAPER = 'paper'
    TYPE_MOCK_TEST = 'mock_test'
    TYPE_CONTRIBUTION = 'contribution'
    TYPE_CUSTOM = 'custom'

    TYPE_CHOICES = [
        (TYPE_REPLY, 'Discussion Reply'),
        (TYPE_PAPER, 'New Question Paper'),
        (TYPE_MOCK_TEST, 'New Mock Test'),
        (TYPE_CONTRIBUTION, 'Answer Contribution'),
        (TYPE_CUSTOM, 'Custom'),
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
