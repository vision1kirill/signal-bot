from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bot", "0003_bot_platform"),
    ]

    operations = [
        migrations.AddField(
            model_name="bot",
            name="api_partner_id",
            field=models.CharField(
                blank=True,
                default="",
                max_length=50,
                verbose_name="API Partner ID (CleverAff)",
            ),
        ),
        migrations.AddField(
            model_name="bot",
            name="api_key",
            field=models.CharField(
                blank=True,
                default="",
                max_length=200,
                verbose_name="API Key (CleverAff)",
            ),
        ),
    ]
