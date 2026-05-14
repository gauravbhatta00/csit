from accounts.models import Notification


def notify_reply(discussion_owner, replier_username, discussion):
    Notification.objects.create(
        user=discussion_owner,
        type=Notification.TYPE_REPLY,
        message=f"{replier_username} replied to '{discussion.title}'.",
        link_path=(
            f"/semester/{discussion.subject.semester.slug}"
            f"/subject/{discussion.subject.slug}#discussions"
        ),
    )


def notify_payment(user, plan_name, amount):
    Notification.objects.create(
        user=user,
        type=Notification.TYPE_PAYMENT,
        message=f"Payment of Rs. {amount} received for {plan_name}.",
        link_path="/profile",
    )
