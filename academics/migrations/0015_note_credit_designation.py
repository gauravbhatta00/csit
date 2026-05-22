from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('academics', '0014_question_source_metadata'),
    ]

    operations = [
        migrations.AddField(
            model_name='note',
            name='credit_designation',
            field=models.CharField(blank=True, max_length=160),
        ),
    ]
