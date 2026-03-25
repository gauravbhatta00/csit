from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.utils import timezone


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
    is_premium = models.BooleanField(default=False)
    premium_expires_at = models.DateTimeField(null=True, blank=True)
    active_token = models.CharField(max_length=255, null=True, blank=True)

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