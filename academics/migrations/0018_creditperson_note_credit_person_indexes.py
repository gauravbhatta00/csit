import django.db.models.deletion
from django.db import migrations, models


def backfill_credit_people(apps, schema_editor):
    CreditPerson = apps.get_model('academics', 'CreditPerson')
    Note = apps.get_model('academics', 'Note')

    notes = Note.objects.exclude(credit_name='').filter(credit_person__isnull=True)
    for note in notes.iterator(chunk_size=200):
        image_name = note.credit_image.name if note.credit_image else ''
        person, _ = CreditPerson.objects.get_or_create(
            name=note.credit_name,
            designation=note.credit_designation,
            link_url=note.credit_url,
            image=image_name,
            defaults={
                'image_url': '',
                'portfolio_url': '',
            },
        )
        note.credit_person = person
        note.save(update_fields=['credit_person'])


def clear_backfilled_credit_people(apps, schema_editor):
    Note = apps.get_model('academics', 'Note')
    Note.objects.update(credit_person=None)


class Migration(migrations.Migration):

    dependencies = [
        ('academics', '0017_answercontribution_is_main_answer'),
    ]

    operations = [
        migrations.CreateModel(
            name='CreditPerson',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120)),
                ('designation', models.CharField(blank=True, max_length=160)),
                ('link_url', models.URLField(blank=True)),
                ('image', models.ImageField(blank=True, null=True, upload_to='notes/credits/')),
                ('image_url', models.URLField(blank=True)),
                ('portfolio_url', models.URLField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['name', 'designation'],
            },
        ),
        migrations.AddField(
            model_name='note',
            name='credit_person',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='notes', to='academics.creditperson'),
        ),
        migrations.AddIndex(
            model_name='creditperson',
            index=models.Index(fields=['name'], name='credit_person_name_idx'),
        ),
        migrations.AddIndex(
            model_name='note',
            index=models.Index(fields=['subject', 'is_published', 'unit', 'order'], name='note_sub_pub_unit_ord_idx'),
        ),
        migrations.AddIndex(
            model_name='question',
            index=models.Index(fields=['year', 'section', 'order'], name='question_year_sec_ord_idx'),
        ),
        migrations.AddIndex(
            model_name='answercontribution',
            index=models.Index(fields=['question', 'status', 'is_main_answer'], name='ans_contrib_q_status_idx'),
        ),
        migrations.AddIndex(
            model_name='mocktestresult',
            index=models.Index(fields=['user', 'completed_at'], name='mock_result_user_time_idx'),
        ),
        migrations.AddIndex(
            model_name='discussion',
            index=models.Index(fields=['subject', 'created_at'], name='discussion_subject_time_idx'),
        ),
        migrations.RunPython(backfill_credit_people, clear_backfilled_credit_people),
    ]
