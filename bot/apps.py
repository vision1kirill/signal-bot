from django.apps import AppConfig


class BotConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "bot"

    def ready(self):
        import bot.signals  # регистрируем сигналы django

        from django.core.signals import request_started
        from .models import Bot

        def reset_bots(sender, **kwargs):
            """
            сбрасываем флаг is_active для всех ботов при первом запросе.
            это нужно потому что треды не переживают перезапуск сервера —
            боты в памяти пропадают, а в бд остаётся is_active=True.
            """
            if getattr(reset_bots, "done", False):
                return
            reset_bots.done = True
            try:
                # таблица может не существовать при первой миграции
                Bot.objects.all().update(is_active=False)
            except Exception:
                pass  # db ещё не готова — пропускаем

        request_started.connect(reset_bots)
