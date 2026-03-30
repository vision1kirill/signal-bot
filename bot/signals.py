"""
django-сигналы для автоматических действий при изменении моделей.
также содержит дефолтные данные для создания нового бота.
"""

import threading
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone

from .models import (
    Bot, Message, Image, Link, Postback, BotAccess,
    User, MultiChat, BotMarketing, Channel
)
from bot.utils import send_acess_message_utils, send_marketing, send_deposit_feed_utils


# =========================================================
# изображения по умолчанию
# =========================================================

DEFAULT_IMAGES = [
    {"name": "Шаблонное изображение", "image": "telegram_images/test_message.jpg"},
]

# =========================================================
# сообщения по умолчанию на трёх языках (en / es / pt)
# каждый список — (method, text_en, text_es, text_pt)
# =========================================================

DEFAULT_MESSAGES_I18N = [
    # (метод, en, es, pt)
    (
        "hello",
        "👋 Welcome! Press the button below to start.",
        "👋 ¡Bienvenido! Presiona el botón para comenzar.",
        "👋 Bem-vindo! Pressione o botão para começar.",
    ),
    (
        "menu",
        "📋 Main Menu",
        "📋 Menú Principal",
        "📋 Menu Principal",
    ),
    (
        "about_1",
        "ℹ️ About us — page 1",
        "ℹ️ Sobre nosotros — página 1",
        "ℹ️ Sobre nós — página 1",
    ),
    (
        "about_2",
        "ℹ️ About us — page 2",
        "ℹ️ Sobre nosotros — página 2",
        "ℹ️ Sobre nós — página 2",
    ),
    (
        "access_info",
        "📝 Register via the referral link below to get access.",
        "📝 Regístrate usando el enlace de referido para obtener acceso.",
        "📝 Registre-se pelo link de referência para obter acesso.",
    ),
    (
        "get_user_id",
        "🔢 Enter your platform User ID:",
        "🔢 Ingresa tu ID de usuario de la plataforma:",
        "🔢 Digite seu ID de usuário da plataforma:",
    ),
    (
        "get_user_id_error",
        "❌ ID not found or already linked to another account.",
        "❌ ID no encontrado o ya vinculado a otra cuenta.",
        "❌ ID não encontrado ou já vinculado a outra conta.",
    ),
    (
        "get_deposit",
        "💰 Please make your first deposit to unlock full access.",
        "💰 Por favor realiza tu primer depósito para desbloquear el acceso completo.",
        "💰 Por favor, faça seu primeiro depósito para desbloquear o acesso completo.",
    ),
    (
        "new_access",
        "🎉 Full access activated! You can now receive signals.",
        "🎉 ¡Acceso completo activado! Ahora puedes recibir señales.",
        "🎉 Acesso completo ativado! Agora você pode receber sinais.",
    ),
    (
        "get_market",
        "📈 Select a market:",
        "📈 Selecciona un mercado:",
        "📈 Selecione um mercado:",
    ),
    (
        "get_pair",
        "💱 Select a currency pair:",
        "💱 Selecciona un par de divisas:",
        "💱 Selecione um par de moedas:",
    ),
    (
        "get_expiration",
        "⏱ Select expiration time:",
        "⏱ Selecciona el tiempo de expiración:",
        "⏱ Selecione o tempo de expiração:",
    ),
    (
        "animation_1",
        "🔍 Scanning market...",
        "🔍 Escaneando el mercado...",
        "🔍 Escaneando o mercado...",
    ),
    (
        "animation_2",
        "📊 Analyzing indicators...",
        "📊 Analizando indicadores...",
        "📊 Analisando indicadores...",
    ),
    (
        "animation_3",
        "🧠 AI generating signal...",
        "🧠 IA generando señal...",
        "🧠 IA gerando sinal...",
    ),
    # тексты для сигналов не требуют перевода — они генерируются динамически
    ("signal_higher", "", "", ""),
    ("signal_lower", "", "", ""),
    (
        "temp_access_info",
        (
            "⏳ <b>Free Test</b>\n\n"
            "You will have access for <b>10 minutes</b>.\n"
            "⚠️ Demo mode — signals are not accurate."
        ),
        (
            "⏳ <b>Prueba Gratuita</b>\n\n"
            "Tendrás acceso durante <b>10 minutos</b>.\n"
            "⚠️ Modo demo — las señales no son precisas."
        ),
        (
            "⏳ <b>Teste Gratuito</b>\n\n"
            "Você terá acesso por <b>10 minutos</b>.\n"
            "⚠️ Modo demo — os sinais não são precisos."
        ),
    ),
    (
        "temp_access_over",
        (
            "⏰ Your free test has ended.\n\n"
            "Activate the bot to get full access to signals."
        ),
        (
            "⏰ Tu prueba gratuita ha terminado.\n\n"
            "Activa el bot para obtener acceso completo a las señales."
        ),
        (
            "⏰ Seu teste gratuito terminou.\n\n"
            "Ative o bot para ter acesso completo aos sinais."
        ),
    ),
    (
        "temp_access",
        "⚠️ <b>Demo mode</b> — signals may be inaccurate.",
        "⚠️ <b>Modo demo</b> — las señales pueden ser inexactas.",
        "⚠️ <b>Modo demo</b> — os sinais podem ser imprecisos.",
    ),
]

# =========================================================
# ссылки по умолчанию
# =========================================================

DEFAULT_LINKS = [
    {"name": "Отзывы", "method": "reviews", "url": "https://t.me/reviews"},
    {"name": "Поддержка", "method": "support", "url": "https://t.me/support"},
    {"name": "Реферальная ссылка Pocket Option", "method": "ref",
     "url": "https://po.trade/signup?lid=00000"},
]

# =========================================================
# каналы по умолчанию
# =========================================================

DEFAULT_CHANNELS = [
    {"name": "Постбэки", "method": "postback", "channel_id": ""},
    {"name": "Feed", "method": "feed", "channel_id": ""},
]


# =========================================================
# сигнал: создание нового бота — создаём дефолтные данные
# =========================================================

@receiver(post_save, sender=Bot)
def create_default_objects(sender, instance, created, **kwargs):
    """при создании нового бота автоматически создаёт сообщения, ссылки и каналы."""
    if not created:
        return

    # создаём изображения по умолчанию
    images = []
    for img_data in DEFAULT_IMAGES:
        img_obj = Image.objects.create(bot=instance, **img_data)
        images.append(img_obj)

    default_image = images[0] if images else None

    # создаём сообщения для всех трёх языков
    for row in DEFAULT_MESSAGES_I18N:
        method = row[0]
        texts = {"en": row[1], "es": row[2], "pt": row[3]}
        for lang, text in texts.items():
            Message.objects.get_or_create(
                bot=instance,
                method=method,
                language=lang,
                defaults={
                    "text": text,
                    "image": default_image,
                },
            )

    # создаём ссылки
    for link_data in DEFAULT_LINKS:
        Link.objects.get_or_create(bot=instance, method=link_data["method"],
                                   defaults=link_data)

    # создаём каналы
    for channel_data in DEFAULT_CHANNELS:
        Channel.objects.get_or_create(bot=instance, method=channel_data["method"],
                                      defaults=channel_data)


# =========================================================
# сигнал: обновление постбэка — автовыдача доступа
# =========================================================

@receiver(post_save, sender=Postback)
def update_bot_access(sender, instance, created, **kwargs):
    """
    при обновлении постбэка с флагом deposit=True:
    1. уведомляет feed о депозите
    2. проверяет минимальный депозит
    3. автоматически выдаёт полный доступ если сумма >= min_deposit
    """
    if created or not instance.deposit or not instance.bot or not instance.chat_id:
        return

    bot_instance = instance.bot
    chat_id = instance.chat_id

    # уведомляем feed о депозите
    send_deposit_feed_utils(bot_instance, chat_id)

    # проверяем минимальный депозит
    min_dep = bot_instance.min_deposit
    deposit_amount = instance.deposit_amount

    if min_dep and min_dep > 0:
        if deposit_amount is None or deposit_amount < min_dep:
            # депозит меньше минимального — доступ не выдаём
            return

    # выдаём полный доступ
    BotAccess.objects.get_or_create(bot=bot_instance, chat_id=chat_id)


# =========================================================
# сигнал: выдача полного доступа — отправляем поздравление
# =========================================================

@receiver(post_save, sender=BotAccess)
def send_access_message(sender, instance, created, **kwargs):
    """отправляет сообщение о получении полного доступа при первом создании записи."""
    if created:
        send_acess_message_utils(instance.bot, instance.chat_id)


# =========================================================
# сигнал: удаление мультичата — очищаем topic_id у пользователей
# =========================================================

@receiver(post_delete, sender=MultiChat)
def clear_topic_ids(sender, instance, **kwargs):
    """при удалении мультичата сбрасываем id топиков у пользователей."""
    User.objects.filter(bot=instance.bot, topic_id__isnull=False).update(topic_id=None)


# =========================================================
# сигнал: создание рассылки — запускаем отправку
# =========================================================

@receiver(post_save, sender=BotMarketing)
def create_marketing(sender, instance, created, **kwargs):
    """
    при создании рассылки запускает её отправку.
    если задано scheduled_at — ставит таймер на нужное время.
    если нет — отправляет немедленно.
    """
    if not created or instance.sent:
        return

    if instance.scheduled_at and instance.scheduled_at > timezone.now():
        # вычисляем задержку в секундах
        delay = (instance.scheduled_at - timezone.now()).total_seconds()

        def _delayed_send():
            # перечитываем из бд на случай если запись изменилась
            try:
                fresh = BotMarketing.objects.get(pk=instance.pk)
                if not fresh.sent:
                    send_marketing(fresh.bot, fresh)
                    BotMarketing.objects.filter(pk=instance.pk).update(sent=True)
            except BotMarketing.DoesNotExist:
                pass

        timer = threading.Timer(delay, _delayed_send)
        timer.daemon = True
        timer.start()
    else:
        send_marketing(instance.bot, instance)
        BotMarketing.objects.filter(pk=instance.pk).update(sent=True)
