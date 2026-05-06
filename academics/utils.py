# academics/utils.py
from accounts.models import Notification


def send_notification(user, type, message):
    """Helper to create notification for a user."""
    Notification.objects.create(
        user=user,
        type=type,
        message=message
    )


def notify_reply(discussion_owner, replier_username, discussion_title):
    """Notify discussion owner when someone replies."""
    send_notification(
        user=discussion_owner,
        type='reply',
        message=f"{replier_username} replied to your discussion: '{discussion_title}'"
    )


def notify_new_paper(users, subject_name, year):
    """Notify all users when new question paper is added."""
    for user in users:
        send_notification(
            user=user,
            type='paper',
            message=f"New {year} question paper added for {subject_name}"
        )


def notify_payment(user, plan_name, amount):
    """Notify user when payment is successful."""
    send_notification(
        user=user,
        type='payment',
        message=f"Payment of Rs.{amount // 100} successful. {plan_name} activated!"
    )


def notify_premium_expiry(user, days_left):
    """Notify user when premium is about to expire."""
    send_notification(
        user=user,
        type='premium_expiry',
        message=f"Your premium expires in {days_left} days. Renew now to keep access."
    )