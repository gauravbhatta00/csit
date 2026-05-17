from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('academics', '0005_answercontribution'),
    ]

    operations = [
        migrations.AddField(
            model_name='answercontribution',
            name='image',
            field=models.ImageField(blank=True, null=True, upload_to='answer_contributions/'),
        ),
    ]
