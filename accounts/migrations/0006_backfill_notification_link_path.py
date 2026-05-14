from django.db import migrations


def backfill_notification_links(apps, schema_editor):
    Notification = apps.get_model('accounts', 'Notification')
    Discussion = apps.get_model('academics', 'Discussion')

    for notification in Notification.objects.filter(link_path=''):
        if notification.type == 'payment':
            notification.link_path = '/profile'
            notification.save(update_fields=['link_path'])
            continue

        if notification.type != 'reply':
            continue

        title_start = notification.message.find("'")
        title_end = notification.message.rfind("'")

        if title_start == -1 or title_end <= title_start:
            continue

        title = notification.message[title_start + 1:title_end]
        discussion = (
            Discussion.objects.filter(
                user=notification.user,
                title=title,
            )
            .select_related('subject__semester')
            .first()
        )

        if not discussion:
            continue

        notification.link_path = (
            f"/semester/{discussion.subject.semester.slug}"
            f"/subject/{discussion.subject.slug}#discussions"
        )
        notification.save(update_fields=['link_path'])


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_notification_link_path'),
        ('academics', '0003_discussion_discussionreply_mocktest_mocktestquestion_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_notification_links, migrations.RunPython.noop),
    ]
