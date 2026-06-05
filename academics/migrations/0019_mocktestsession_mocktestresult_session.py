from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('academics', '0018_creditperson_note_credit_person_indexes'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='MockTestSession',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('question_ids', models.JSONField(default=list)),
                ('question_count', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('mock_test', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sessions', to='academics.mocktest')),
                ('source_session', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='retake_sessions', to='academics.mocktestsession')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='mock_test_sessions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddField(
            model_name='mocktestresult',
            name='session',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='result', to='academics.mocktestsession'),
        ),
        migrations.AddIndex(
            model_name='mocktestsession',
            index=models.Index(fields=['user', 'mock_test', 'created_at'], name='mock_session_user_test_idx'),
        ),
    ]
