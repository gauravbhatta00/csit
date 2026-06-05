import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


DEFAULT_EMAIL_TEMPLATES = [
    {
        'slug': 'study-update',
        'name': 'Study update',
        'subject': 'New CSIT resources are ready',
        'preheader': 'Fresh notes, questions, and updates from Ramro CSIT.',
        'body_html': (
            '<h2>Fresh CSIT resources are ready</h2>'
            '<p>We have added new study resources to help you revise faster.</p>'
            '<p><a class="button" href="{{ frontend_url }}">Browse resources</a></p>'
        ),
        'custom_css': '',
    },
    {
        'slug': 'exam-reminder',
        'name': 'Exam reminder',
        'subject': 'Plan your next CSIT revision session',
        'preheader': 'A focused reminder for upcoming CSIT preparation.',
        'body_html': (
            '<h2>Keep your revision moving</h2>'
            '<p>Use recent questions, syllabus units, and notes to plan your next session.</p>'
            '<p><a class="button" href="{{ frontend_url }}/semester">Open semesters</a></p>'
        ),
        'custom_css': '',
    },
    {
        'slug': 'custom-announcement',
        'name': 'Custom announcement',
        'subject': 'A quick update from Ramro CSIT',
        'preheader': 'A short update for CSIT students.',
        'body_html': (
            '<h2>Ramro CSIT update</h2>'
            '<p>Write your announcement here.</p>'
            '<p><a class="button" href="{{ frontend_url }}">Visit Ramro CSIT</a></p>'
        ),
        'custom_css': '',
    },
]


def backfill_email_subscriptions(apps, schema_editor):
    User = apps.get_model('accounts', 'CustomUser')
    EmailSubscription = apps.get_model('accounts', 'EmailSubscription')
    for user in User.objects.exclude(email=''):
        email = user.email.strip().lower()
        if not email:
            continue
        subscription = EmailSubscription.objects.filter(email__iexact=email).first()
        if subscription:
            subscription.email = email
            subscription.is_active = True
            subscription.source = 'existing_user'
            subscription.save(update_fields=['email', 'is_active', 'source'])
        else:
            EmailSubscription.objects.create(
                email=email,
                is_active=True,
                source='existing_user',
            )


def backfill_unsubscribe_tokens(apps, schema_editor):
    EmailSubscription = apps.get_model('accounts', 'EmailSubscription')
    for subscription in EmailSubscription.objects.filter(unsubscribe_token__isnull=True):
        subscription.unsubscribe_token = uuid.uuid4()
        subscription.save(update_fields=['unsubscribe_token'])


def seed_email_templates(apps, schema_editor):
    EmailTemplate = apps.get_model('accounts', 'EmailTemplate')
    for template in DEFAULT_EMAIL_TEMPLATES:
        EmailTemplate.objects.update_or_create(
            slug=template['slug'],
            defaults={**template, 'is_system': True},
        )


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0017_devicetoken'),
    ]

    operations = [
        migrations.AddField(
            model_name='emailsubscription',
            name='source',
            field=models.CharField(default='manual', max_length=40),
        ),
        migrations.AddField(
            model_name='emailsubscription',
            name='unsubscribe_token',
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.CreateModel(
            name='EmailTemplate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('slug', models.SlugField(unique=True)),
                ('name', models.CharField(max_length=120)),
                ('subject', models.CharField(max_length=180)),
                ('preheader', models.CharField(blank=True, max_length=220)),
                ('body_html', models.TextField()),
                ('custom_css', models.TextField(blank=True)),
                ('is_system', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='EmailCampaign',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('subject', models.CharField(max_length=180)),
                ('preheader', models.CharField(blank=True, max_length=220)),
                ('body_html', models.TextField()),
                ('custom_css', models.TextField(blank=True)),
                ('recipient_filter', models.CharField(choices=[('active_subscribers', 'Active subscribers'), ('all_users', 'All users with email')], default='active_subscribers', max_length=40)),
                ('sent_count', models.PositiveIntegerField(default=0)),
                ('failed_count', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('sent_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='sent_email_campaigns', to=settings.AUTH_USER_MODEL)),
                ('template', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='campaigns', to='accounts.emailtemplate')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.RunPython(backfill_email_subscriptions, migrations.RunPython.noop),
        migrations.RunPython(backfill_unsubscribe_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='emailsubscription',
            name='unsubscribe_token',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.RunPython(seed_email_templates, migrations.RunPython.noop),
    ]
