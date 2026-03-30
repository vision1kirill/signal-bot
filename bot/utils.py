"""
утилиты для управления ботами: запуск, остановка, рассылки.
все функции работают с активными экземплярами botов через active_bots.
"""

import threading
import logging
import os

from django.db import close_old_connections

from .models import Bot, User, BotAccess, TempAccess, BotMarketing, Channel
from .bot import new_bot, send_access_message, send_deposit_feed

logger = logging.getLogger(__name__)

# словарь активных ботов: {bot_id: {"bot": TeleBot, "thread": Thread}}
active_bots = {}


# =========================================================
# управление жизненным циклом бота
# =========================================================

def run_bot_instance(bot_instance: Bot):
    """
    запускает polling-цикл бота в отдельном потоке.
    при сетевых ошибках автоматически перезапускает polling
    с экспоненциальной задержкой (5 → 10 → 20 → ... → 120 сек).
    """
    retry_delay = 5   # начальная задержка перезапуска в секундах
    max_delay   = 120 # максимальная задержка

    # закрываем унаследованные соединения из основного процесса —
    # SQLite не thread-safe, каждый поток должен открыть своё соединение
    close_old_connections()

    while bot_instance.id in active_bots:
        try:
            bot = new_bot(bot_instance)
            active_bots[bot_instance.id]["bot"] = bot
            logger.info("бот '%s': polling запущен", bot_instance.name)
            # infinity_polling сам ловит сетевые ошибки; завершается только при stop_polling()
            bot.infinity_polling(timeout=60, long_polling_timeout=30, logger_level=None)
            # нормальное завершение (вызов stop_polling) — выходим из цикла
            logger.info("бот '%s': polling завершён штатно", bot_instance.name)
            break
        except Exception as e:
            if bot_instance.id not in active_bots:
                # бот был остановлен вручную — не перезапускаем
                break
            logger.error(
                "бот '%s': ошибка polling: %s — перезапуск через %d сек",
                bot_instance.name, e, retry_delay,
            )
            threading.Event().wait(retry_delay)        # ждём без блокировки GIL
            retry_delay = min(retry_delay * 2, max_delay)

    # итоговая очистка
    Bot.objects.filter(id=bot_instance.id).update(is_active=False)
    active_bots.pop(bot_instance.id, None)
    logger.info("бот '%s' остановлен", bot_instance.name)


def start_bot(bot_instance: Bot):
    """запускает бота если он ещё не запущен."""
    if bot_instance.id in active_bots:
        logger.warning("бот '%s' уже запущен", bot_instance.name)
        return

    Bot.objects.filter(id=bot_instance.id).update(is_active=True)

    # ВАЖНО: добавляем запись в active_bots ДО старта потока —
    # иначе поток может проверить словарь раньше чем мы его заполним
    # и сразу выйти из while-цикла (race condition)
    active_bots[bot_instance.id] = {"thread": None, "bot": None}

    thread = threading.Thread(
        target=run_bot_instance,
        args=(bot_instance,),
        daemon=True,
        name=f"bot-{bot_instance.id}",
    )
    thread.start()

    active_bots[bot_instance.id]["thread"] = thread
    logger.info("бот '%s' запущен (thread=%s)", bot_instance.name, thread.name)


def stop_bot(bot_instance: Bot):
    """корректно останавливает бота."""
    data = active_bots.get(bot_instance.id)
    if not data:
        logger.warning("бот '%s' не найден среди активных", bot_instance.name)
        return

    bot = data.get("bot")
    if bot:
        try:
            bot.stop_polling()
        except Exception as e:
            logger.warning("ошибка при остановке polling: %s", e)

    thread = data.get("thread")
    if thread and thread.is_alive():
        thread.join(timeout=10)

    Bot.objects.filter(id=bot_instance.id).update(is_active=False)
    active_bots.pop(bot_instance.id, None)
    logger.info("бот '%s' остановлен вручную", bot_instance.name)


# =========================================================
# обёртки для использования из django-сигналов
# =========================================================

def send_acess_message_utils(bot_instance: Bot, chat_id: str):
    """отправляет сообщение о выдаче полного доступа через отдельный экземпляр бота."""
    try:
        bot = new_bot(bot_instance)
        send_access_message(bot, chat_id)
    except Exception as e:
        logger.error(
            "ошибка send_access_message для бота '%s', chat_id=%s: %s",
            bot_instance.name, chat_id, e,
        )


def send_deposit_feed_utils(bot_instance: Bot, chat_id: str):
    """уведомляет feed-канал о новом депозите."""
    try:
        bot = new_bot(bot_instance)
        send_deposit_feed(bot, chat_id)
    except Exception as e:
        logger.error(
            "ошибка send_deposit_feed для бота '%s', chat_id=%s: %s",
            bot_instance.name, chat_id, e,
        )


# =========================================================
# рассылка сообщений с сегментацией аудитории
# =========================================================

def _get_target_chat_ids(bot_instance: Bot, segment: str, language_filter: str = "all") -> list:
    """
    возвращает список chat_id для нужного сегмента с опциональной фильтрацией по языку.

    сегменты:
        all       — все пользователи бота
        no_access — без доступа (нет ни теста ни полного)
        test      — только тестовый доступ (без полного)
        full      — только полный доступ

    language_filter:
        all / en / es / pt
    """
    qs = User.objects.filter(bot=bot_instance)
    # фильтр по языку: берём только пользователей с нужным языком
    if language_filter and language_filter != "all":
        qs = qs.filter(language=language_filter)

    all_users = qs.values_list("chat_id", flat=True)

    if segment == "all":
        return list(all_users)

    full_access_ids = set(
        BotAccess.objects.filter(bot=bot_instance).values_list("chat_id", flat=True)
    )
    test_access_ids = set(
        TempAccess.objects.filter(bot=bot_instance).values_list("chat_id", flat=True)
    )

    if segment == "full":
        return [cid for cid in all_users if cid in full_access_ids]

    if segment == "test":
        # только тестовый — не имеет полного доступа
        return [cid for cid in all_users if cid in test_access_ids and cid not in full_access_ids]

    if segment == "no_access":
        # нет ни тестового ни полного
        return [cid for cid in all_users if cid not in test_access_ids and cid not in full_access_ids]

    return list(all_users)


def send_marketing(bot_instance: Bot, marketing_instance: BotMarketing):
    """
    отправляет рассылку пользователям выбранного сегмента.
    поддерживает текст и изображение, фильтрацию по языку.
    после отправки удаляет временный файл изображения.
    """
    bot = new_bot(bot_instance)
    segment = getattr(marketing_instance, "segment", "all")
    language_filter = getattr(marketing_instance, "language_filter", "all")
    target_ids = _get_target_chat_ids(bot_instance, segment, language_filter)

    image_path = marketing_instance.image.path if marketing_instance.image else None

    sent = 0
    failed = 0
    for chat_id in target_ids:
        try:
            text = marketing_instance.text
            if image_path:
                with open(image_path, "rb") as photo:
                    bot.send_photo(
                        chat_id, photo, caption=text, parse_mode="HTML"
                    )
            else:
                bot.send_message(chat_id, text, parse_mode="HTML")
            sent += 1
        except Exception as e:
            failed += 1
            logger.warning(
                "рассылка: не удалось отправить chat_id=%s: %s", chat_id, e
            )

    logger.info(
        "рассылка '%s' завершена: отправлено=%d, ошибок=%d",
        marketing_instance, sent, failed,
    )

    # удаляем временное изображение после отправки
    if image_path and os.path.exists(image_path):
        try:
            os.remove(image_path)
        except OSError as e:
            logger.warning("не удалось удалить файл рассылки %s: %s", image_path, e)


# =========================================================
# уведомление в канал о постбэке
# =========================================================

def send_postback(data: dict, bot_instance=None):
    """
    отправляет уведомление в postback-канал о новом событии.
    используется из crm/views.py.

    bot_instance — экземпляр Bot для фильтрации нужного канала.
    если не передан — берётся первый попавшийся канал (fallback).
    """
    qs = Channel.objects.filter(method="postback").exclude(channel_id="")
    # bug-fix: фильтруем по боту чтобы не слать в чужой канал
    if bot_instance is not None:
        qs = qs.filter(bot=bot_instance)
    channel_obj = qs.first()

    if not channel_obj:
        return

    try:
        bot = new_bot(channel_obj.bot)

        status = data.get("status", "")
        uid = data.get("uid", "—")
        lid = data.get("lid", "—")
        payout = data.get("payout", "—")

        if status == "reg":
            text = (
                "🆕 <b>Новая регистрация</b>\n"
                f"🔑 ID реф. ссылки: <code>{lid}</code>\n"
                f"👤 ID пользователя: <code>{uid}</code>"
            )
        else:
            text = (
                "💰 <b>Новый депозит (FTD)</b>\n"
                f"🔑 ID реф. ссылки: <code>{lid}</code>\n"
                f"👤 ID пользователя: <code>{uid}</code>\n"
                f"💵 Сумма: <code>{payout}</code>"
            )

        bot.send_message(
            channel_obj.channel_id, text, parse_mode="HTML"
        )
    except Exception as e:
        logger.error("ошибка отправки в postback-канал: %s", e)
