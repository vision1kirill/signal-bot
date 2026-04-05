"""
конфигурация приложения bot.
при старте сервера автоматически запускает все боты с is_active=True.
"""

import sys
import logging
import threading

from django.apps import AppConfig

logger = logging.getLogger(__name__)

# manage.py команды при которых боты не нужны
_SKIP_AUTOSTART_COMMANDS = {
    "migrate", "makemigrations", "shell", "shell_plus",
    "test", "collectstatic", "createsuperuser", "check",
    "showmigrations", "sqlmigrate", "dbshell", "dumpdata", "loaddata",
}


class BotConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "bot"

    def ready(self):
        import bot.signals  # регистрируем django-сигналы

        # пропускаем авто-старт при выполнении manage.py команд
        argv = sys.argv
        if len(argv) > 1 and argv[1] in _SKIP_AUTOSTART_COMMANDS:
            return

        # небольшая задержка чтобы Django и пул соединений с БД
        # полностью инициализировались перед первым ORM-запросом
        timer = threading.Timer(2.0, self._autostart_bots)
        timer.daemon = True
        timer.start()

    def _autostart_bots(self):
        """Запускает все боты у которых is_active=True в БД."""
        try:
            from .models import Bot
            from .utils import start_bot, active_bots

            bots = list(Bot.objects.filter(is_active=True))
            if not bots:
                logger.info("авто-старт: активных ботов не найдено")
                return

            for bot_obj in bots:
                # не запускаем повторно если бот уже в памяти
                if bot_obj.id in active_bots:
                    continue
                try:
                    start_bot(bot_obj)
                    logger.info("авто-старт: бот '%s' запущен", bot_obj.name)
                except Exception as e:
                    logger.error(
                        "авто-старт: не удалось запустить бота '%s': %s",
                        bot_obj.name, e,
                    )

        except Exception as e:
            logger.error("авто-старт: ошибка: %s", e)
