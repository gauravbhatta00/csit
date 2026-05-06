from accounts.models import Notification


def notify_reply(discussion_owner, replier_username, discussion_title):
    Notification.objects.create(
        user=discussion_owner,
        type=Notification.TYPE_REPLY,
        message=f"{replier_username} replied to '{discussion_title}'.",
    )


def notify_payment(user, plan_name, amount):
    Notification.objects.create(
        user=user,
        type=Notification.TYPE_PAYMENT,
        message=f"Payment of Rs. {amount} received for {plan_name}.",
    )
