from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bot", "0002_updates"),
    ]

    operations = [
        migrations.AddField(
            model_name="bot",
            name="platform",
            field=models.CharField(
                choices=[
                    ("pocket", "Pocket Option"),
                    ("binarium", "Binarium (CleverAff)"),
                ],
                default="pocket",
                max_length=32,
                verbose_name="Платформа",
            ),
        ),
    ]
