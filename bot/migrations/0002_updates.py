"""
миграция 0002 — обновления моделей:
  - Bot: добавлено поле ref_id
  - CustomSignal: удалено поле text, добавлено поле order
  - BotMarketing: добавлены поля language_filter, scheduled_at, sent
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bot", "0001_initial"),
    ]

    operations = [
        # --- Bot: добавляем ref_id ---
        migrations.AddField(
            model_name="bot",
            name="ref_id",
            field=models.CharField(
                blank=True,
                default="",
                max_length=100,
                verbose_name="ID реферальной ссылки (lid / aff_id)",
            ),
        ),

        # --- CustomSignal: убираем text, добавляем order ---
        migrations.RemoveField(
            model_name="customsignal",
            name="text",
        ),
        migrations.AddField(
            model_name="customsignal",
            name="order",
            field=models.PositiveIntegerField(
                default=1,
                verbose_name="Порядок (1 = следующий)",
            ),
        ),
        migrations.AlterModelOptions(
            name="customsignal",
            options={
                "ordering": ["order"],
                "verbose_name": "Кастомный сигнал",
                "verbose_name_plural": "Кастомные сигналы",
            },
        ),

        # --- BotMarketing: добавляем language_filter, scheduled_at, sent ---
        migrations.AddField(
            model_name="botmarketing",
            name="language_filter",
            field=models.CharField(
                choices=[
                    ("all", "Все языки"),
                    ("en", "English 🇬🇧"),
                    ("es", "Español 🇪🇸"),
                    ("pt", "Português 🇵🇹"),
                ],
                default="all",
                max_length=10,
                verbose_name="Язык аудитории",
            ),
        ),
        migrations.AddField(
            model_name="botmarketing",
            name="scheduled_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="Запланировать на (оставьте пустым для немедленной отправки)",
            ),
        ),
        migrations.AddField(
            model_name="botmarketing",
            name="sent",
            field=models.BooleanField(
                default=False,
                verbose_name="Отправлено",
            ),
        ),
    ]
