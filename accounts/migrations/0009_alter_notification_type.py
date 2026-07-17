from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('accounts', '0008_emailsubscription')]

    operations = [
        migrations.AlterField(
            model_name='notification',
            name='type',
            field=models.CharField(
                choices=[
                    ('general', 'General'),
                    ('reply', 'Discussion Reply'),
                    ('paper', 'New Question Paper'),
                    ('mock_test', 'New Mock Test'),
                    ('premium_expiry', 'Premium Expiring'),
                    ('payment', 'Payment'),
                ],
                max_length=20,
            ),
        ),
    ]
