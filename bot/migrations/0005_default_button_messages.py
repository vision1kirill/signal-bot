"""
Дата-миграция: создаёт дефолтные записи сообщений для кнопок (btn_*)
и pending-сообщения (get_user_id_pending) для всех существующих ботов.

Записи создаются только если их ещё нет (get_or_create).
Языки: en, es, pt.
"""
from django.db import migrations

# дефолтные тексты кнопок на всех языках
DEFAULT_BUTTONS = {
    "btn_start": {
        "en": "▶️ Start Bot",
        "es": "▶️ Iniciar Bot",
        "pt": "▶️ Iniciar Bot",
    },
    "btn_activate": {
        "en": "🚀 Activate Bot",
        "es": "🚀 Activar Bot",
        "pt": "🚀 Ativar Bot",
    },
    "btn_free_test": {
        "en": "🆓 Free Test",
        "es": "🆓 Prueba Gratis",
        "pt": "🆓 Teste Grátis",
    },
    "btn_signal": {
        "en": "📊 Get Signal",
        "es": "📊 Obtener Señal",
        "pt": "📊 Obter Sinal",
    },
    "btn_reviews": {
        "en": "⭐ Reviews",
        "es": "⭐ Reseñas",
        "pt": "⭐ Avaliações",
    },
    "btn_support": {
        "en": "💬 Support",
        "es": "💬 Soporte",
        "pt": "💬 Suporte",
    },
    "btn_about": {
        "en": "ℹ️ About Us",
        "es": "ℹ️ Sobre Nosotros",
        "pt": "ℹ️ Sobre Nós",
    },
    "btn_language": {
        "en": "🌍 Language",
        "es": "🌍 Idioma",
        "pt": "🌍 Idioma",
    },
    "btn_back": {
        "en": "◀️ Back",
        "es": "◀️ Atrás",
        "pt": "◀️ Voltar",
    },
    "btn_retry": {
        "en": "🔄 Try Again",
        "es": "🔄 Intentar de Nuevo",
        "pt": "🔄 Tentar Novamente",
    },
    "get_user_id_pending": {
        "en": (
            "⏳ <b>Registration is being processed.</b>\n\n"
            "After registering on the platform, it takes up to <b>3 minutes</b> "
            "for your account to appear in the system.\n\n"
            "Please wait and tap <b>Try Again</b>."
        ),
        "es": (
            "⏳ <b>El registro está siendo procesado.</b>\n\n"
            "Después de registrarte, puede tardar hasta <b>3 minutos</b> "
            "para que tu cuenta aparezca en el sistema.\n\n"
            "Por favor espera y presiona <b>Intentar de Nuevo</b>."
        ),
        "pt": (
            "⏳ <b>O registro está sendo processado.</b>\n\n"
            "Após o cadastro, pode levar até <b>3 minutos</b> "
            "para que sua conta apareça no sistema.\n\n"
            "Por favor, aguarde e toque em <b>Tentar Novamente</b>."
        ),
    },
}


def create_default_messages(apps, schema_editor):
    Bot = apps.get_model("bot", "Bot")
    Message = apps.get_model("bot", "Message")

    for bot in Bot.objects.all():
        for method, translations in DEFAULT_BUTTONS.items():
            for language, text in translations.items():
                Message.objects.get_or_create(
                    bot=bot,
                    method=method,
                    language=language,
                    defaults={"text": text},
                )


def reverse_default_messages(apps, schema_editor):
    # при откате миграции не удаляем — могут быть пользовательские правки
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("bot", "0004_bot_api_fields"),
    ]

    operations = [
        migrations.RunPython(
            create_default_messages,
            reverse_default_messages,
        ),
    ]
