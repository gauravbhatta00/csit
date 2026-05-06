
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from accounts.models import CustomUser
from academics.utils import notify_premium_expiry


class Command(BaseCommand):
    help = 'Check premium expiry and send notifications'

    def handle(self, *args, **kwargs):
        now = timezone.now()

        # ✅ Notify users expiring in 3 days
        expiring_soon = CustomUser.objects.filter(
            is_premium=True,
            premium_expires_at__lte=now + timedelta(days=3),
            premium_expires_at__gte=now
        )

        for user in expiring_soon:
            days_left = (user.premium_expires_at - now).days
            notify_premium_expiry(user, days_left)
            self.stdout.write(f"Notified {user.username} - {days_left} days left")

        self.stdout.write('Done checking premium expiry.')