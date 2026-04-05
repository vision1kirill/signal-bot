"""
основная логика telegram-бота.
каждый экземпляр бота запускается через new_bot() и работает в отдельном потоке.
"""

import os
import time
import random
import logging

from telebot import TeleBot, types
from telebot.apihelper import ApiException
from django.utils import timezone
from datetime import timedelta

from decimal import Decimal

from .models import (
    Bot, Message, Link, BotAccess, Postback,
    TempAccess, User, MultiChat, CustomSignal, Channel
)
from crm.models import Market, Pair, Expiration
from .pixel import send_lead_event  # для события привязки платформенного id
from .cleveraff_api import check_gamer, PLAYER_NOT_FOUND  # API CleverAff для Binarium

logger = logging.getLogger(__name__)


def _resolve_postback(bot_instance: Bot, entered_id: str, lid: str) -> "Postback | None":
    """
    Находит или создаёт Postback для пользователя.

    Для Binarium (если заданы api_partner_id и api_key):
        — вызывает CleverAff API мгновенно, без ожидания постбэка.
        — если API вернул 404 → пользователь не наш → None.
        — если API недоступен → fallback на локальную БД.

    Для Pocket и остальных платформ:
        — ищет в локальной БД (стандартная логика).

    Возвращает объект Postback (ещё не привязан к chat_id) или None.
    """
    if (
        bot_instance.platform == "binarium"
        and bot_instance.api_partner_id
        and bot_instance.api_key
    ):
        api_data = check_gamer(
            entered_id,
            partner_id=bot_instance.api_partner_id,
            api_key=bot_instance.api_key,
        )

        if api_data is PLAYER_NOT_FOUND:
            # HTTP 404 — игрок точно не наш, не смотрим в локальную БД
            logger.info("_resolve_postback: uid=%s не наш (404 от CleverAff)", entered_id)
            return None

        if api_data is not None:
            # игрок наш — берём существующий постбэк или создаём новый
            postback_obj = (
                Postback.objects.filter(user_id=entered_id, chat_id="").first()
                or Postback.objects.create(
                    user_id=entered_id,
                    link_id=lid or "",
                    chat_id="",
                    bot=bot_instance,
                )
            )

            # если API уже знает о депозите — фиксируем его сразу
            if api_data.get("dep") and not postback_obj.deposit:
                stats = api_data.get("stats") or {}
                ftd_amount = stats.get("ftd_amount")
                postback_obj.deposit = True
                postback_obj.deposit_amount = (
                    Decimal(str(ftd_amount)) if ftd_amount is not None else None
                )
                postback_obj.deposited_at = timezone.now()

            return postback_obj

        # api_data is None — временная ошибка API (timeout, 5xx)
        # пробуем локальную БД как запасной вариант
        logger.warning(
            "CleverAff API временно недоступен для uid=%s, проверяем локальную БД",
            entered_id,
        )

    # стандартный поиск по локальной БД (Pocket + fallback для Binarium)
    postback_obj = None
    if lid:
        postback_obj = Postback.objects.filter(
            user_id=entered_id, chat_id="", link_id=lid
        ).first()
    if not postback_obj:
        postback_obj = Postback.objects.filter(
            user_id=entered_id, chat_id=""
        ).first()
    return postback_obj

def _get_btn(bot_instance: "Bot", method_key: str, lang: str, default: str) -> str:
    """
    Возвращает текст кнопки из модели Message (метод btn_*).
    Если не задан в нужном языке — fallback на 'en', затем на default.
    Можно использовать как внутри new_bot(), так и снаружи.
    """
    text = (
        Message.objects.filter(bot=bot_instance, method=method_key, language=lang)
        .values_list("text", flat=True).first()
        or Message.objects.filter(bot=bot_instance, method=method_key, language="en")
        .values_list("text", flat=True).first()
    )
    return text or default


# =========================================================
# переводы текста сигнала по языкам
# =========================================================

_SIGNAL_I18N = {
    "en": {
        "demo_label":        "⚠️ <i>Demo mode. Signals are not accurate</i>",
        "locked":            "🔐 Locked",
        "higher":            "🟢 HIGHER",
        "lower":             "🔴 LOWER",
        "overview":          "🔍 Overview",
        "price_levels":      "📐 Price Levels",
        "indicators":        "📊 Indicators",
        "signal_strength":   "✅ Signal Strength",
        "volatility":        "Volatility",
        "asset_strength":    "Asset Strength",
        "volume":            "Volume",
        "sentiment":         "Sentiment",
        "price":             "Price",
        "resistance":        "Resistance (R1)",
        "support":           "Support (S1)",
        "rsi":               "RSI",
        "macd":              "MACD",
        "ma":                "MA",
        "strength":          "Strength",
        "conditions":        "Conditions",
        "expiration":        "Expiration",
        "direction":         "Direction",
        "volatility_options": ["Low", "Medium", "High", "Above average", "Extreme"],
        "sentiment_options":  ["Strong bullish", "Bullish", "Neutral",
                               "Bearish", "Strong bearish",
                               "Upward pressure", "Downward pressure"],
        "rsi_options":        ["Overbought", "Oversold", "Neutral",
                               "Peak level", "Low", "Mid"],
        "macd_options":       ["Bullish divergence", "Bearish divergence",
                               "Buying pressure", "Selling pressure"],
        "ma_options":         ["Upward trend", "Downward trend",
                               "Resistance test", "Support test"],
        "condition_options":  ["Weak", "Neutral", "Optimal", "Strong", "Critical"],
    },
    "es": {
        "demo_label":        "⚠️ <i>Modo demo. Las señales no son precisas</i>",
        "locked":            "🔐 Bloqueado",
        "higher":            "🟢 ALCISTA",
        "lower":             "🔴 BAJISTA",
        "overview":          "🔍 Resumen",
        "price_levels":      "📐 Niveles de Precio",
        "indicators":        "📊 Indicadores",
        "signal_strength":   "✅ Fuerza de la Señal",
        "volatility":        "Volatilidad",
        "asset_strength":    "Fuerza del Activo",
        "volume":            "Volumen",
        "sentiment":         "Sentimiento",
        "price":             "Precio",
        "resistance":        "Resistencia (R1)",
        "support":           "Soporte (S1)",
        "rsi":               "RSI",
        "macd":              "MACD",
        "ma":                "MA",
        "strength":          "Fuerza",
        "conditions":        "Condiciones",
        "expiration":        "Expiración",
        "direction":         "Dirección",
        "volatility_options": ["Baja", "Media", "Alta", "Por encima del promedio", "Extrema"],
        "sentiment_options":  ["Muy alcista", "Alcista", "Neutral",
                               "Bajista", "Muy bajista",
                               "Presión alcista", "Presión bajista"],
        "rsi_options":        ["Sobrecomprado", "Sobrevendido", "Neutral",
                               "Nivel máximo", "Bajo", "Medio"],
        "macd_options":       ["Divergencia alcista", "Divergencia bajista",
                               "Presión compradora", "Presión vendedora"],
        "ma_options":         ["Tendencia alcista", "Tendencia bajista",
                               "Prueba de resistencia", "Prueba de soporte"],
        "condition_options":  ["Débil", "Neutral", "Óptimo", "Fuerte", "Crítico"],
    },
    "pt": {
        "demo_label":        "⚠️ <i>Modo demo. Os sinais não são precisos</i>",
        "locked":            "🔐 Bloqueado",
        "higher":            "🟢 ALTA",
        "lower":             "🔴 BAIXA",
        "overview":          "🔍 Visão Geral",
        "price_levels":      "📐 Níveis de Preço",
        "indicators":        "📊 Indicadores",
        "signal_strength":   "✅ Força do Sinal",
        "volatility":        "Volatilidade",
        "asset_strength":    "Força do Ativo",
        "volume":            "Volume",
        "sentiment":         "Sentimento",
        "price":             "Preço",
        "resistance":        "Resistência (R1)",
        "support":           "Suporte (S1)",
        "rsi":               "RSI",
        "macd":              "MACD",
        "ma":                "MA",
        "strength":          "Força",
        "conditions":        "Condições",
        "expiration":        "Expiração",
        "direction":         "Direção",
        "volatility_options": ["Baixa", "Média", "Alta", "Acima da média", "Extrema"],
        "sentiment_options":  ["Muito altista", "Altista", "Neutro",
                               "Baixista", "Muito baixista",
                               "Pressão altista", "Pressão baixista"],
        "rsi_options":        ["Sobrecomprado", "Sobrevendido", "Neutro",
                               "Nível máximo", "Baixo", "Médio"],
        "macd_options":       ["Divergência altista", "Divergência baixista",
                               "Pressão compradora", "Pressão vendedora"],
        "ma_options":         ["Tendência altista", "Tendência baixista",
                               "Teste de resistência", "Teste de suporte"],
        "condition_options":  ["Fraco", "Neutro", "Ótimo", "Forte", "Crítico"],
    },
}


# карта языковых кодов telegram → коды языков бота
LANG_MAP = {
    "es": "es",
    "pt": "pt",
    "pt-br": "pt",
    "pt_br": "pt",
}

# метки языков для кнопок выбора
LANG_LABELS = {
    "en": "🇬🇧 English",
    "es": "🇪🇸 Español",
    "pt": "🇵🇹 Português",
}


def detect_language(telegram_lang_code: str) -> str:
    """определяет язык по коду интерфейса telegram. по умолчанию английский."""
    if not telegram_lang_code:
        return "en"
    code = telegram_lang_code.lower().replace("-", "_")
    # проверяем точное совпадение, потом префикс
    if code in LANG_MAP:
        return LANG_MAP[code]
    prefix = code.split("_")[0]
    return LANG_MAP.get(prefix, "en")


def get_user_language(bot_instance: Bot, chat_id) -> str:
    """возвращает язык пользователя из бд. fallback — английский."""
    user = User.objects.filter(bot=bot_instance, chat_id=str(chat_id)).first()
    return user.language if user else "en"


def new_bot(bot_instance: Bot):
    """
    создаёт и настраивает экземпляр telebot для заданного бота.
    загружает все сообщения, ссылки, рынки и экспирации из бд.
    возвращает готовый к polling объект бота.
    """
    bot = TeleBot(bot_instance.token)
    bot.bot_instance = bot_instance

    # --- загрузка сообщений сгруппированных по языку ---
    # структура: {lang: {method: {text, image}}}
    messages = Message.objects.filter(bot=bot_instance).select_related("image")
    result = {}
    for msg in messages:
        lang = msg.language
        if lang not in result:
            result[lang] = {}
        result[lang][msg.method] = {
            "text": msg.text or "",
            "image": msg.image.image.path if msg.image else None,
        }
    bot.result = result

    # --- загрузка ссылок ---
    links = Link.objects.filter(bot=bot_instance)
    result_links = {link.method: link.url for link in links}
    bot.result_links = result_links

    # --- загрузка рынков и пар ---
    markets = Market.objects.all()
    result_markets = [market.name for market in markets]

    pairs = Pair.objects.select_related("market").all()
    result_pairs = {}
    for pair in pairs:
        market_name = pair.market.name
        if market_name not in result_pairs:
            result_pairs[market_name] = []
        result_pairs[market_name].append({
            "symbol": pair.symbol,
            "price": float(pair.price) if pair.price is not None else None,
        })

    # --- загрузка экспираций ---
    expirations = Expiration.objects.all()
    result_expirations = [exp.label for exp in expirations]

    # =========================================================
    # вспомогательная функция отправки/редактирования сообщений
    # =========================================================

    def send_message_by_method(
        chat_id, method, language="en", edit=False,
        message_id=None, keyboard=None
    ):
        """
        отправляет или редактирует сообщение по кодовому имени (method).
        если метод содержит 'signal' — формирует текст сигнала динамически.
        язык используется для выбора нужного перевода. fallback на 'en'.
        """
        data = method.split(" ")
        method_key = data[0]

        directions = None

        # для сигналов определяем направление рандомно или из очереди кастомных
        if method_key == "signal":
            # берём первый сигнал из очереди (наименьший order)
            custom_first = CustomSignal.objects.filter(
                bot=bot_instance, chat_id=str(chat_id)
            ).order_by("order").first()

            if custom_first:
                directions = custom_first.direction
                # потребляем сигнал из очереди — удаляем его
                custom_first.delete()
            else:
                directions = random.choice(["higher", "lower"])

            method_key = "signal_" + directions

        # свежий запрос к БД — изменения в админке отражаются без перезапуска
        msg_db = (
            Message.objects.filter(
                bot=bot_instance, method=method_key, language=language
            ).select_related("image").first()
            or Message.objects.filter(
                bot=bot_instance, method=method_key, language="en"
            ).select_related("image").first()
        )
        if not msg_db:
            logger.warning("сообщение с методом '%s' не найдено", method_key)
            return
        msg_data = {
            "text": msg_db.text or "",
            "image": msg_db.image.image.path if msg_db.image else None,
        }

        # --- формирование текста сигнала ---
        # direction уже определён выше (из очереди кастомных или рандомно)
        if "signal" in method_key:
            has_full_access = BotAccess.objects.filter(
                bot=bot_instance, chat_id=str(chat_id)
            ).exists()

            # берём переводы для текущего языка, fallback → en
            i18n = _SIGNAL_I18N.get(language) or _SIGNAL_I18N["en"]

            if has_full_access:
                rsi_options       = i18n["rsi_options"]
                macd_options      = i18n["macd_options"]
                ma_options        = i18n["ma_options"]
                condition_options = i18n["condition_options"]
                strength          = random.randint(80, 99)
                demo_label        = ""
            else:
                # демо-режим — ограниченные данные
                locked            = i18n["locked"]
                rsi_options       = [locked]
                macd_options      = [locked]
                ma_options        = [locked]
                condition_options = [locked]
                strength          = locked
                demo_label        = "\n" + i18n["demo_label"] + "\n"

            direction_label = i18n["higher"] if directions == "higher" else i18n["lower"]

            # извлекаем данные пары и экспирации из callback_data
            try:
                pair_symbol = result_pairs[result_markets[int(data[1])]][int(data[2])]["symbol"]
                price = result_pairs[result_markets[int(data[1])]][int(data[2])]["price"]
                expiration = result_expirations[int(data[3])]
            except (IndexError, KeyError, ValueError) as e:
                logger.error("ошибка парсинга данных сигнала: %s", e)
                return

            t = i18n  # короткий алиас
            text  = f"{demo_label}"
            text += f"<b>{pair_symbol}</b>\n\n"
            text += f"{t['overview']}:\n"
            text += f"• {t['volatility']}: <code>{random.choice(t['volatility_options'])}</code> ⚡️\n"
            text += f"• {t['asset_strength']}: <code>{random.randint(20, 90)}%</code> 💪\n"
            text += f"• {t['volume']}: <code>{random.randint(20, 90)}%</code> 📦\n"
            text += f"• {t['sentiment']}: <code>{random.choice(t['sentiment_options'])}</code> 📊\n\n"
            text += f"{t['price_levels']}:\n"
            text += f"• {t['price']}: <code>{price}</code> 💵\n"
            text += f"• {t['resistance']}: <code>{price}</code> 🛑\n"
            text += f"• {t['support']}: <code>{price}</code> 🟢\n\n"
            text += f"{t['indicators']}:\n"
            text += f"• {t['rsi']}: <code>{random.choice(rsi_options)}</code>\n"
            text += f"• {t['macd']}: <code>{random.choice(macd_options)}</code>\n"
            text += f"• {t['ma']}: <code>{random.choice(ma_options)}</code>\n\n"
            text += f"{t['signal_strength']}:\n"
            text += f"• {t['strength']}: <code>{strength}%</code> 🧠\n"
            text += f"• {t['conditions']}: <code>{random.choice(condition_options)}</code>\n\n"
            text += f"📅 {t['expiration']}: <code>{expiration}</code>\n"
            text += f"📊 {t['direction']}: <code>{direction_label}</code>\n"
        else:
            text = msg_data.get("text", "")

        image_path = msg_data.get("image")
        # bug-fix: проверяем что файл реально существует на диске
        if image_path and not os.path.exists(image_path):
            logger.warning("файл изображения не найден: %s — отправляю без фото", image_path)
            image_path = None

        # --- отправка или редактирование ---
        try:
            if edit and message_id:
                if image_path:
                    try:
                        with open(image_path, "rb") as photo:
                            bot.edit_message_media(
                                chat_id=chat_id,
                                message_id=message_id,
                                media=types.InputMediaPhoto(
                                    photo, caption=text, parse_mode="HTML"
                                ),
                                reply_markup=keyboard,
                            )
                        return
                    except ApiException as e:
                        if "message is not modified" in str(e).lower():
                            return
                        # если не удалось отредактировать медиа — шлём новым сообщением
                else:
                    try:
                        bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=text,
                            parse_mode="HTML",
                            reply_markup=keyboard,
                        )
                        return
                    except ApiException as e:
                        if "message is not modified" in str(e).lower():
                            return
        except Exception as e:
            logger.warning("не удалось отредактировать сообщение: %s", e)

        # отправка нового сообщения
        try:
            if image_path:
                with open(image_path, "rb") as photo:
                    bot.send_photo(
                        chat_id, photo, caption=text,
                        parse_mode="HTML", reply_markup=keyboard
                    )
            else:
                bot.send_message(
                    chat_id, text, parse_mode="HTML", reply_markup=keyboard
                )
        except ApiException as e:
            logger.error("ошибка отправки сообщения chat_id=%s: %s", chat_id, e)

    bot.send_message_by_method = send_message_by_method

    # =========================================================
    # вспомогательная функция — текст кнопки из БД
    # =========================================================

    def get_btn(method_key: str, lang: str, default: str) -> str:
        """Тонкая обёртка над модульной _get_btn с захваченным bot_instance."""
        return _get_btn(bot_instance, method_key, lang, default)

    # =========================================================
    # вспомогательная функция — кнопки главного меню
    # =========================================================

    def build_menu_keyboard(chat_id, lang="en"):
        """строит клавиатуру главного меню в зависимости от статуса доступа."""
        buttons = []
        if BotAccess.objects.filter(bot=bot_instance, chat_id=str(chat_id)).exists():
            buttons.append([
                types.InlineKeyboardButton(
                    text=get_btn("btn_signal", lang, "📊 Получить сигнал"),
                    callback_data="signal",
                )
            ])
        else:
            buttons += [
                [types.InlineKeyboardButton(
                    text=get_btn("btn_activate", lang, "🚀 Активировать бота"),
                    callback_data="access",
                )],
                [types.InlineKeyboardButton(
                    text=get_btn("btn_free_test", lang, "🆓 Бесплатный тест"),
                    callback_data="temp_access",
                )],
            ]

        reviews_url = result_links.get("reviews", "https://t.me/")
        support_url = result_links.get("support", "https://t.me/")

        buttons += [
            [
                types.InlineKeyboardButton(
                    text=get_btn("btn_reviews", lang, "⭐ Отзывы"), url=reviews_url
                ),
                types.InlineKeyboardButton(
                    text=get_btn("btn_support", lang, "💬 Поддержка"), url=support_url
                ),
            ],
            [types.InlineKeyboardButton(
                text=get_btn("btn_about", lang, "ℹ️ О нас"), callback_data="about"
            )],
            [types.InlineKeyboardButton(
                text=get_btn("btn_language", lang, "🌍 Язык / Language"),
                callback_data="language",
            )],
        ]
        return types.InlineKeyboardMarkup(buttons)

    # =========================================================
    # /start — точка входа пользователя
    # =========================================================

    @bot.message_handler(commands=["start"])
    def start(message):
        chat_id = str(message.chat.id)

        # определяем язык по настройкам telegram
        tg_lang = getattr(message.from_user, "language_code", None)
        detected_lang = detect_language(tg_lang)

        # создаём пользователя или получаем существующего
        user_obj, created = User.objects.get_or_create(
            bot=bot_instance, chat_id=chat_id
        )

        # обновляем username и язык при первом входе
        if created:
            user_obj.language = detected_lang
            user_obj.username = message.from_user.username or ""
            user_obj.save()

            # отправляем уведомление в feed-канал о новом пользователе
            _notify_feed(
                "Пользователь @%s (%s)\nВход в бота" % (
                    message.from_user.username, message.from_user.id
                )
            )

        # создаём топик в мультичате для нового пользователя
        if user_obj.topic_id is None:
            _create_multichat_topic(bot, bot_instance, user_obj, message.from_user)

        lang = user_obj.language
        keyboard = types.InlineKeyboardMarkup([[
            types.InlineKeyboardButton(
                text=get_btn("btn_start", lang, "▶️ Запустить бота"),
                callback_data="menu",
            )
        ]])
        send_message_by_method(chat_id, "hello", language=lang, keyboard=keyboard)

    # =========================================================
    # пересылка сообщений между пользователем и оператором
    # =========================================================

    @bot.message_handler(content_types=["text"])
    def handle_all_text(message):
        """перенаправляет текст между пользователем и топиком оператора."""
        if message.chat.type in ["group", "supergroup"]:
            # сообщение из группы — пересылаем пользователю
            multi_chat_obj = MultiChat.objects.filter(bot=bot_instance).first()
            if not multi_chat_obj:
                return
            if str(message.chat.id) != str(multi_chat_obj.channel_id):
                return
            thread_id = getattr(message, "message_thread_id", None)
            if thread_id:
                user_obj = User.objects.filter(
                    bot=bot_instance, topic_id=str(thread_id)
                ).first()
                if user_obj:
                    try:
                        bot.send_message(user_obj.chat_id, message.text)
                    except ApiException as e:
                        logger.warning(
                            "не удалось переслать сообщение пользователю %s: %s",
                            user_obj.chat_id, e
                        )
        else:
            # сообщение от пользователя — пересылаем в топик
            user_obj = User.objects.filter(
                bot=bot_instance, chat_id=str(message.chat.id)
            ).first()
            if user_obj and user_obj.topic_id:
                multi_chat_obj = MultiChat.objects.filter(bot=bot_instance).first()
                if multi_chat_obj:
                    try:
                        bot.send_message(
                            multi_chat_obj.channel_id,
                            message.text,
                            message_thread_id=int(user_obj.topic_id),
                        )
                    except ApiException as e:
                        logger.warning(
                            "не удалось переслать сообщение в топик: %s", e
                        )

    # =========================================================
    # главное меню
    # =========================================================

    @bot.callback_query_handler(func=lambda call: call.data == "menu")
    def menu(call):
        bot.clear_step_handler(call.message)
        lang = get_user_language(bot_instance, call.message.chat.id)
        keyboard = build_menu_keyboard(call.message.chat.id, lang)
        send_message_by_method(
            call.message.chat.id, "menu", language=lang,
            edit=True, message_id=call.message.message_id, keyboard=keyboard
        )

    # =========================================================
    # о нас — листание страниц
    # =========================================================

    @bot.callback_query_handler(func=lambda call: call.data.startswith("about"))
    def about(call):
        data = call.data.split("_")
        page = int(data[1]) if len(data) > 1 else 1
        lang = get_user_language(bot_instance, call.message.chat.id)
        lang_result = result.get(lang) or result.get("en") or {}
        count = sum(1 for key in lang_result if key.startswith("about"))

        if count == 0:
            return

        next_page = 1 if page == count else page + 1
        prev_page = count if page == 1 else page - 1

        buttons = [
            [
                types.InlineKeyboardButton(text="◀", callback_data=f"about_{prev_page}"),
                types.InlineKeyboardButton(
                    text=f"{page}/{count}", callback_data="none"
                ),
                types.InlineKeyboardButton(text="▶", callback_data=f"about_{next_page}"),
            ],
            [types.InlineKeyboardButton(
                text=get_btn("btn_back", lang, "◀️ Назад"), callback_data="menu"
            )],
        ]
        keyboard = types.InlineKeyboardMarkup(buttons)
        send_message_by_method(
            call.message.chat.id, f"about_{page}", language=lang,
            edit=True, message_id=call.message.message_id, keyboard=keyboard
        )

    # =========================================================
    # выбор языка
    # =========================================================

    @bot.callback_query_handler(func=lambda call: call.data == "language")
    def language_menu(call):
        """показывает меню выбора языка."""
        lang = get_user_language(bot_instance, call.message.chat.id)
        buttons = [
            [types.InlineKeyboardButton(
                text=label, callback_data=f"set_lang_{code}"
            )]
            for code, label in LANG_LABELS.items()
        ]
        buttons.append([
            types.InlineKeyboardButton(
                text=get_btn("btn_back", lang, "◀️ Назад"), callback_data="menu"
            )
        ])
        keyboard = types.InlineKeyboardMarkup(buttons)
        lang_text = "🌍 Choose your language / Elige tu idioma / Escolha seu idioma:"
        try:
            # пытаемся отредактировать текущее сообщение
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=lang_text,
                reply_markup=keyboard,
            )
        except ApiException:
            # если сообщение с фото — edit_message_text не работает, шлём новым
            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except Exception:
                pass
            bot.send_message(call.message.chat.id, lang_text, reply_markup=keyboard)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("set_lang_"))
    def set_language(call):
        """сохраняет выбранный язык пользователя."""
        lang_code = call.data.replace("set_lang_", "")
        if lang_code not in LANG_LABELS:
            return

        User.objects.filter(
            bot=bot_instance, chat_id=str(call.message.chat.id)
        ).update(language=lang_code)

        confirmation = {
            "en": "✅ Language set to English",
            "es": "✅ Idioma establecido en Español",
            "pt": "✅ Idioma definido para Português",
        }
        try:
            bot.answer_callback_query(
                call.id, confirmation.get(lang_code, "✅ Done")
            )
        except Exception:
            pass

        # возвращаемся в меню с новым языком
        keyboard = build_menu_keyboard(call.message.chat.id, lang_code)
        lang_result = result.get(lang_code) or result.get("en") or {}
        menu_data = lang_result.get("menu")
        if menu_data:
            text = menu_data.get("text", "")
            image_path = menu_data.get("image")
            try:
                if image_path:
                    with open(image_path, "rb") as photo:
                        bot.edit_message_media(
                            chat_id=call.message.chat.id,
                            message_id=call.message.message_id,
                            media=types.InputMediaPhoto(
                                photo, caption=text, parse_mode="HTML"
                            ),
                            reply_markup=keyboard,
                        )
                else:
                    bot.edit_message_text(
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        text=text,
                        parse_mode="HTML",
                        reply_markup=keyboard,
                    )
            except Exception:
                send_message_by_method(
                    call.message.chat.id, "menu", language=lang_code, keyboard=keyboard
                )

    # =========================================================
    # активация бота (ftd-воронка)
    # =========================================================

    @bot.callback_query_handler(func=lambda call: call.data == "access")
    def access(call):
        lang = get_user_language(bot_instance, call.message.chat.id)
        postback_obj = Postback.objects.filter(
            bot=bot_instance, chat_id=str(call.message.chat.id)
        ).first()

        if not postback_obj:
            # пользователь ещё не регистрировался по реф-ссылке
            ref_url = result_links.get("ref", "https://t.me/")
            buttons = [
                [types.InlineKeyboardButton(
                    text=get_btn("btn_register", lang, "📝 Зарегистрироваться"),
                    url=ref_url,
                )],
                [types.InlineKeyboardButton(
                    text=get_btn("btn_check_reg", lang, "✅ Проверить регистрацию"),
                    callback_data="get_user_id",
                )],
                [types.InlineKeyboardButton(
                    text=get_btn("btn_back", lang, "◀️ Назад"), callback_data="menu"
                )],
            ]
            keyboard = types.InlineKeyboardMarkup(buttons)
            send_message_by_method(
                call.message.chat.id, "access_info", language=lang,
                edit=True, message_id=call.message.message_id, keyboard=keyboard
            )
        elif not postback_obj.deposit:
            # зарегистрировался, но ещё не пополнил депозит
            support_url = result_links.get("support", "https://t.me/")
            buttons = [
                [types.InlineKeyboardButton(
                    text=get_btn("btn_support", lang, "💬 Поддержка"), url=support_url
                )],
                [types.InlineKeyboardButton(
                    text=get_btn("btn_back", lang, "◀️ Назад"), callback_data="menu"
                )],
            ]
            keyboard = types.InlineKeyboardMarkup(buttons)
            send_message_by_method(
                call.message.chat.id, "get_deposit", language=lang,
                edit=True, message_id=call.message.message_id, keyboard=keyboard
            )
        else:
            # депозит есть — выдаём полный доступ
            BotAccess.objects.get_or_create(
                bot=bot_instance, chat_id=str(call.message.chat.id)
            )

    # =========================================================
    # ввод id платформы пользователем
    # =========================================================

    @bot.callback_query_handler(func=lambda call: call.data == "get_user_id")
    def get_user_id(call):
        lang = get_user_language(bot_instance, call.message.chat.id)
        support_url = result_links.get("support", "https://t.me/")
        buttons = [
            [types.InlineKeyboardButton(
                text=get_btn("btn_support", lang, "💬 Поддержка"), url=support_url
            )],
            [types.InlineKeyboardButton(
                text=get_btn("btn_back", lang, "◀️ Назад"), callback_data="menu"
            )],
        ]
        keyboard = types.InlineKeyboardMarkup(buttons)
        send_message_by_method(
            call.message.chat.id, "get_user_id", language=lang,
            edit=True, message_id=call.message.message_id, keyboard=keyboard
        )
        bot.register_next_step_handler(call.message, get_user_id_handler)

    def get_user_id_handler(message):
        """обрабатывает введённый пользователем id платформы."""
        lang = get_user_language(bot_instance, message.chat.id)
        support_url = result_links.get("support", "https://t.me/")

        # приоритет: поле ref_id бота → парсим из url реф-ссылки
        lid = bot_instance.ref_id or ""
        if not lid:
            ref_url = result_links.get("ref", "")
            # поддерживаем разные параметры разных платформ
            for param_name in ["lid=", "aff_id=", "ref=", "partner=", "offer_id="]:
                if param_name in ref_url:
                    lid = ref_url.split(param_name, 1)[1].split("&", 1)[0]
                    break

        entered_id = message.text.strip()

        # проверяем: не занят ли этот id другим аккаунтом
        # сначала точный поиск по lid, затем fallback без lid — на случай расхождения
        already_claimed = Postback.objects.filter(
            user_id=entered_id
        ).exclude(chat_id="").first()
        if already_claimed:
            # этот platform id уже привязан к другому telegram-аккаунту
            buttons = [
                [types.InlineKeyboardButton(
                    text=get_btn("btn_support", lang, "💬 Поддержка"), url=support_url
                )],
                [types.InlineKeyboardButton(
                    text=get_btn("btn_back", lang, "◀️ Назад"), callback_data="menu"
                )],
            ]
            keyboard = types.InlineKeyboardMarkup(buttons)
            send_message_by_method(
                message.chat.id, "get_user_id_error", language=lang, keyboard=keyboard
            )
            return

        # ищем постбэк: Binarium — через API, остальные — через БД
        postback_obj = _resolve_postback(bot_instance, entered_id, lid)

        if postback_obj:
            postback_obj.chat_id = str(message.chat.id)
            postback_obj.bot = bot_instance
            postback_obj.save()

            # bug-fix: pixel Lead event — теперь когда chat_id и bot известны
            try:
                send_lead_event(bot_instance, str(message.chat.id))
            except Exception as e:
                logger.warning("pixel lead event error: %s", e)

            if postback_obj.deposit:
                # депозит уже был — выдаём доступ немедленно
                BotAccess.objects.get_or_create(
                    bot=bot_instance, chat_id=str(message.chat.id)
                )
                return

            support_url = result_links.get("support", "https://t.me/")
            buttons = [
                [types.InlineKeyboardButton(
                    text=get_btn("btn_support", lang, "💬 Поддержка"), url=support_url
                )],
                [types.InlineKeyboardButton(
                    text=get_btn("btn_back", lang, "◀️ Назад"), callback_data="menu"
                )],
            ]
            keyboard = types.InlineKeyboardMarkup(buttons)
            send_message_by_method(
                message.chat.id, "get_deposit", language=lang, keyboard=keyboard
            )
        else:
            support_url = result_links.get("support", "https://t.me/")

            # для Binarium ID может ещё не появиться в системе CleverAff
            # (их данные обновляются каждые ~3 минуты)
            if bot_instance.platform == "binarium":
                buttons = [
                    [types.InlineKeyboardButton(
                        text=get_btn("btn_retry", lang, "🔄 Попробовать снова"),
                        callback_data="access",
                    )],
                    [types.InlineKeyboardButton(
                        text=get_btn("btn_support", lang, "💬 Поддержка"),
                        url=support_url,
                    )],
                    [types.InlineKeyboardButton(
                        text=get_btn("btn_back", lang, "◀️ Назад"),
                        callback_data="menu",
                    )],
                ]
                keyboard = types.InlineKeyboardMarkup(buttons)

                # если в БД настроено сообщение get_user_id_pending — используем его
                # иначе — встроенный текст (пока не добавлен в админке)
                if Message.objects.filter(
                    bot=bot_instance, method="get_user_id_pending"
                ).exists():
                    send_message_by_method(
                        message.chat.id, "get_user_id_pending",
                        language=lang, keyboard=keyboard,
                    )
                else:
                    _pending_texts = {
                        "en": (
                            "⏳ <b>Registration is being processed.</b>\n\n"
                            "After registering on the platform, it takes up to <b>3 minutes</b> "
                            "for your account to appear in the system.\n\n"
                            "Please wait and tap <b>Try again</b>."
                        ),
                        "es": (
                            "⏳ <b>El registro está siendo procesado.</b>\n\n"
                            "Después de registrarte, puede tardar hasta <b>3 minutos</b> "
                            "para que tu cuenta aparezca en el sistema.\n\n"
                            "Por favor espera y presiona <b>Intentar de nuevo</b>."
                        ),
                        "pt": (
                            "⏳ <b>O registro está sendo processado.</b>\n\n"
                            "Após o cadastro, pode levar até <b>3 minutos</b> "
                            "para que sua conta apareça no sistema.\n\n"
                            "Por favor, aguarde e toque em <b>Tentar novamente</b>."
                        ),
                    }
                    try:
                        bot.send_message(
                            message.chat.id,
                            _pending_texts.get(lang, _pending_texts["en"]),
                            parse_mode="HTML", reply_markup=keyboard,
                        )
                    except Exception as e:
                        logger.warning("не удалось отправить pending-сообщение: %s", e)
            else:
                buttons = [
                    [types.InlineKeyboardButton(
                        text=get_btn("btn_support", lang, "💬 Поддержка"),
                        url=support_url,
                    )],
                    [types.InlineKeyboardButton(
                        text=get_btn("btn_back", lang, "◀️ Назад"), callback_data="menu"
                    )],
                ]
                keyboard = types.InlineKeyboardMarkup(buttons)
                send_message_by_method(
                    message.chat.id, "get_user_id_error", language=lang, keyboard=keyboard
                )

    # =========================================================
    # получение сигнала — выбор рынка
    # =========================================================

    @bot.callback_query_handler(func=lambda call: call.data == "signal")
    def signal_start(call):
        """показывает список рынков для выбора."""
        lang = get_user_language(bot_instance, call.message.chat.id)

        # проверяем, не истёк ли тестовый доступ
        if not _check_access(call.message.chat.id, call):
            return

        buttons = [[]]
        count = 0
        for market_id, market in enumerate(result_markets):
            if count >= 2:
                buttons.append([])
                count = 0
            buttons[-1].append(types.InlineKeyboardButton(
                text=market,
                callback_data=f"signal_market 1 {market_id}",
            ))
            count += 1

        buttons.append([types.InlineKeyboardButton(
            text=get_btn("btn_back", lang, "◀️ Назад"), callback_data="menu"
        )])
        keyboard = types.InlineKeyboardMarkup(buttons)
        send_message_by_method(
            call.message.chat.id, "get_market", language=lang,
            edit=True, message_id=call.message.message_id, keyboard=keyboard
        )

    # =========================================================
    # получение сигнала — выбор пары
    # =========================================================

    @bot.callback_query_handler(
        func=lambda call: call.data.startswith("signal_market ")
    )
    def signal_market_handler(call):
        """показывает список валютных пар для выбранного рынка."""
        lang = get_user_language(bot_instance, call.message.chat.id)
        data = call.data.split(" ")
        page = int(data[1])
        market_id = int(data[2])

        if market_id >= len(result_markets):
            return
        market = result_markets[market_id]

        if market not in result_pairs or not result_pairs[market]:
            return

        pairs_data = [
            result_pairs[market][i:i + 8]
            for i in range(0, len(result_pairs[market]), 8)
        ]

        # bug-fix: проверяем что запрошенная страница существует
        if not pairs_data or page < 1 or page > len(pairs_data):
            logger.warning(
                "signal_market_handler: некорректная страница %d (всего %d)",
                page, len(pairs_data)
            )
            return

        buttons = [[]]
        count = 0
        for pair_idx, pair in enumerate(pairs_data[page - 1]):
            if count >= 2:
                buttons.append([])
                count = 0
            global_pair_id = (page - 1) * 8 + pair_idx
            buttons[-1].append(types.InlineKeyboardButton(
                text=pair["symbol"],
                callback_data=f"signal_expiration {market_id} {global_pair_id}",
            ))
            count += 1

        prev_cb = (
            f"signal_market {page - 1} {market_id}" if page > 1 else "none"
        )
        next_cb = (
            f"signal_market {page + 1} {market_id}"
            if page < len(pairs_data) else "none"
        )
        buttons += [
            [
                types.InlineKeyboardButton(text="◀", callback_data=prev_cb),
                types.InlineKeyboardButton(
                    text=f"{page}/{len(pairs_data)}", callback_data="none"
                ),
                types.InlineKeyboardButton(text="▶", callback_data=next_cb),
            ],
            [types.InlineKeyboardButton(
                text=get_btn("btn_back", lang, "◀️ Назад"), callback_data="signal"
            )],
        ]
        keyboard = types.InlineKeyboardMarkup(buttons)
        send_message_by_method(
            call.message.chat.id, "get_pair", language=lang,
            edit=True, message_id=call.message.message_id, keyboard=keyboard
        )

    # =========================================================
    # получение сигнала — выбор экспирации
    # =========================================================

    @bot.callback_query_handler(
        func=lambda call: call.data.startswith("signal_expiration ")
    )
    def signal_expiration_handler(call):
        """показывает доступные экспирации (таймфреймы)."""
        lang = get_user_language(bot_instance, call.message.chat.id)
        data = call.data.split(" ")
        market_id = data[1]
        pair_id = data[2]

        buttons = [[]]
        count = 0
        for exp_id, expiration in enumerate(result_expirations):
            if count >= 3:
                buttons.append([])
                count = 0
            buttons[-1].append(types.InlineKeyboardButton(
                text=expiration,
                callback_data=f"signal_send {market_id} {pair_id} {exp_id}",
            ))
            count += 1

        buttons.append([types.InlineKeyboardButton(
            text=get_btn("btn_back", lang, "◀️ Назад"), callback_data="signal"
        )])
        keyboard = types.InlineKeyboardMarkup(buttons)
        send_message_by_method(
            call.message.chat.id, "get_expiration", language=lang,
            edit=True, message_id=call.message.message_id, keyboard=keyboard
        )

    # =========================================================
    # генерация и отправка сигнала
    # =========================================================

    @bot.callback_query_handler(
        func=lambda call: call.data.startswith("signal_send ")
    )
    def send_signal(call):
        """
        генерирует сигнал с анимацией.
        перед генерацией проверяет тестовый доступ на истечение.
        """
        lang = get_user_language(bot_instance, call.message.chat.id)

        # финальная проверка доступа прямо перед генерацией сигнала
        if not _check_access(call.message.chat.id, call):
            return

        # анимация загрузки
        lang_result = result.get(lang) or result.get("en") or {}
        anim_count = sum(
            1 for key in lang_result if key.startswith("animation")
        )
        for i in range(1, anim_count + 1):
            send_message_by_method(
                call.message.chat.id, f"animation_{i}", language=lang,
                edit=True, message_id=call.message.message_id
            )
            time.sleep(1)

        has_full_access = BotAccess.objects.filter(
            bot=bot_instance, chat_id=str(call.message.chat.id)
        ).exists()

        if has_full_access:
            buttons = [
                [types.InlineKeyboardButton(
                    text=get_btn("btn_new_signal", lang, "🔄 Новый сигнал"),
                    callback_data="signal",
                )],
                [types.InlineKeyboardButton(
                    text=get_btn("btn_menu", lang, "🏠 Меню"), callback_data="menu"
                )],
            ]
        else:
            buttons = [
                [types.InlineKeyboardButton(
                    text=get_btn("btn_menu", lang, "🏠 Меню"), callback_data="menu"
                )]
            ]
        keyboard = types.InlineKeyboardMarkup(buttons)

        # преобразуем callback_data для совместимости с send_message_by_method
        # "signal_send M P E" → "signal M P E"
        signal_data = call.data.replace("signal_send ", "signal ", 1)
        send_message_by_method(
            call.message.chat.id, signal_data, language=lang, keyboard=keyboard
        )

    # =========================================================
    # бесплатный тест
    # =========================================================

    @bot.callback_query_handler(func=lambda call: call.data == "temp_access")
    def temp_access(call):
        lang = get_user_language(bot_instance, call.message.chat.id)
        temp_obj = TempAccess.objects.filter(
            bot=bot_instance, chat_id=str(call.message.chat.id)
        ).first()

        if temp_obj:
            elapsed = timezone.now() - temp_obj.created_at
            if elapsed > timedelta(minutes=10):
                # тест истёк
                buttons = [
                    [types.InlineKeyboardButton(
                        text=get_btn("btn_activate", lang, "🚀 Активировать бота"),
                        callback_data="access",
                    )],
                    [types.InlineKeyboardButton(
                        text=get_btn("btn_back", lang, "◀️ Назад"), callback_data="menu"
                    )],
                ]
                keyboard = types.InlineKeyboardMarkup(buttons)
                send_message_by_method(
                    call.message.chat.id, "temp_access_over", language=lang,
                    edit=True, message_id=call.message.message_id, keyboard=keyboard
                )
            else:
                # тест ещё активен
                remaining = 10 - int(elapsed.total_seconds() / 60)
                buttons = [
                    [types.InlineKeyboardButton(
                        text=get_btn("btn_signal", lang, "📊 Получить сигнал"),
                        callback_data="signal",
                    )],
                    [types.InlineKeyboardButton(
                        text=get_btn("btn_back", lang, "◀️ Назад"), callback_data="menu"
                    )],
                ]
                keyboard = types.InlineKeyboardMarkup(buttons)
                send_message_by_method(
                    call.message.chat.id, "temp_access", language=lang,
                    edit=True, message_id=call.message.message_id, keyboard=keyboard
                )
        else:
            # тест ещё не активировался
            buttons = [
                [types.InlineKeyboardButton(
                    text=get_btn("btn_activate_test", lang, "▶️ Активировать тест"),
                    callback_data="temp_access_activate",
                )],
                [types.InlineKeyboardButton(
                    text=get_btn("btn_back", lang, "◀️ Назад"), callback_data="menu"
                )],
            ]
            keyboard = types.InlineKeyboardMarkup(buttons)
            send_message_by_method(
                call.message.chat.id, "temp_access_info", language=lang,
                edit=True, message_id=call.message.message_id, keyboard=keyboard
            )

    @bot.callback_query_handler(func=lambda call: call.data == "temp_access_activate")
    def temp_access_activate(call):
        lang = get_user_language(bot_instance, call.message.chat.id)
        TempAccess.objects.get_or_create(
            bot=bot_instance, chat_id=str(call.message.chat.id)
        )

        # уведомление в feed
        _notify_feed(
            "Пользователь @%s (%s)\nТестовый доступ" % (
                call.from_user.username, call.from_user.id
            )
        )

        buttons = [
            [types.InlineKeyboardButton(
                text=get_btn("btn_signal", lang, "📊 Получить сигнал"),
                callback_data="signal",
            )],
            [types.InlineKeyboardButton(
                text=get_btn("btn_back", lang, "◀️ Назад"), callback_data="menu"
            )],
        ]
        keyboard = types.InlineKeyboardMarkup(buttons)
        send_message_by_method(
            call.message.chat.id, "temp_access", language=lang,
            edit=True, message_id=call.message.message_id, keyboard=keyboard
        )

    # =========================================================
    # обработчик "нет действия" (пустые кнопки навигации)
    # =========================================================

    @bot.callback_query_handler(func=lambda call: call.data == "none")
    def none_handler(call):
        try:
            bot.answer_callback_query(call.id)
        except Exception:
            pass

    # =========================================================
    # вспомогательные функции
    # =========================================================

    def _notify_feed(text: str):
        """отправляет уведомление в feed-канал если он настроен."""
        channel_obj = Channel.objects.filter(
            bot=bot_instance, method="feed"
        ).exclude(channel_id="").first()
        if channel_obj:
            try:
                bot.send_message(channel_obj.channel_id, text)
            except ApiException as e:
                logger.warning("не удалось отправить в feed: %s", e)

    def _check_access(chat_id, call) -> bool:
        """
        проверяет право на получение сигнала.
        если есть полный доступ — True.
        если есть тестовый и он не истёк — True.
        иначе показывает сообщение об истечении и возвращает False.
        """
        # полный доступ — без ограничений
        if BotAccess.objects.filter(
            bot=bot_instance, chat_id=str(chat_id)
        ).exists():
            return True

        # проверяем тестовый доступ
        temp_obj = TempAccess.objects.filter(
            bot=bot_instance, chat_id=str(chat_id)
        ).first()
        if temp_obj:
            elapsed = timezone.now() - temp_obj.created_at
            if elapsed <= timedelta(minutes=10):
                return True
            # тест истёк — уведомляем пользователя
            lang = get_user_language(bot_instance, chat_id)
            buttons = [
                [types.InlineKeyboardButton(
                    text=get_btn("btn_activate", lang, "🚀 Активировать бота"),
                    callback_data="access",
                )],
                [types.InlineKeyboardButton(
                    text=get_btn("btn_menu", lang, "🏠 Меню"), callback_data="menu"
                )],
            ]
            keyboard = types.InlineKeyboardMarkup(buttons)
            try:
                send_message_by_method(
                    chat_id, "temp_access_over", language=lang,
                    edit=True, message_id=call.message.message_id, keyboard=keyboard
                )
            except Exception:
                send_message_by_method(
                    chat_id, "temp_access_over", language=lang, keyboard=keyboard
                )
            return False

        # bug-fix: нет никакого доступа — перенаправляем в меню с объяснением
        lang = get_user_language(bot_instance, chat_id)
        keyboard = build_menu_keyboard(chat_id, lang)
        try:
            send_message_by_method(
                chat_id, "menu", language=lang,
                edit=True, message_id=call.message.message_id, keyboard=keyboard
            )
        except Exception:
            send_message_by_method(chat_id, "menu", language=lang, keyboard=keyboard)
        return False

    bot.send_message_by_method = send_message_by_method
    return bot


# =========================================================
# вспомогательные функции для сигналов django
# =========================================================

def _create_multichat_topic(bot, bot_instance, user_obj, from_user):
    """создаёт топик в супергруппе для нового пользователя."""
    try:
        multi_chat_obj = MultiChat.objects.filter(bot=bot_instance).first()
        if not multi_chat_obj:
            return
        channel_id = multi_chat_obj.channel_id
        topic = bot.create_forum_topic(
            chat_id=channel_id,
            name="@%s (%s)" % (from_user.username, from_user.id),
        )
        user_obj.topic_id = str(topic.message_thread_id)
        user_obj.save()
        bot.send_message(
            channel_id,
            "Новый пользователь — @%s" % from_user.username,
            message_thread_id=topic.message_thread_id,
        )
    except Exception as e:
        logger.warning("не удалось создать топик мультичата: %s", e)


def send_access_message(bot, chat_id):
    """отправляет сообщение о получении полного доступа."""
    channel_obj = Channel.objects.filter(
        bot=bot.bot_instance, method="feed"
    ).exclude(channel_id="").first()
    if channel_obj:
        try:
            chat = bot.get_chat(chat_id)
            username = getattr(chat, "username", chat_id)
            bot.send_message(
                channel_obj.channel_id,
                "Пользователь @%s (%s)\nПолный доступ" % (username, chat_id),
            )
        except Exception as e:
            logger.warning("не удалось отправить в feed о полном доступе: %s", e)

    lang = get_user_language(bot.bot_instance, chat_id)
    buttons = [[types.InlineKeyboardButton(
        text=_get_btn(bot.bot_instance, "btn_menu", lang, "🏠 Меню"),
        callback_data="menu",
    )]]
    keyboard = types.InlineKeyboardMarkup(buttons)
    bot.send_message_by_method(chat_id, "new_access", language=lang, keyboard=keyboard)


def send_deposit_feed(bot, chat_id):
    """уведомляет feed-канал о получении депозита."""
    channel_obj = Channel.objects.filter(
        bot=bot.bot_instance, method="feed"
    ).exclude(channel_id="").first()
    if channel_obj:
        try:
            chat = bot.get_chat(chat_id)
            username = getattr(chat, "username", chat_id)
            bot.send_message(
                channel_obj.channel_id,
                "Пользователь @%s (%s)\nДепозит" % (username, chat_id),
            )
        except Exception as e:
            logger.warning("не удалось отправить в feed о депозите: %s", e)
