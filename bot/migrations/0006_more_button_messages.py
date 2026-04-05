"""
Дата-миграция: добавляет дефолтные записи для новых кнопок
(btn_register, btn_check_reg, btn_activate_test, btn_new_signal, btn_menu)
для всех существующих ботов.

Записи создаются только если их ещё нет (get_or_create).
Языки: en, es, pt.
"""
from django.db import migrations

NEW_BUTTONS = {
    "btn_register": {
        "en": "📝 Register",
        "es": "📝 Registrarse",
        "pt": "📝 Registrar",
    },
    "btn_check_reg": {
        "en": "✅ Check Registration",
        "es": "✅ Verificar Registro",
        "pt": "✅ Verificar Cadastro",
    },
    "btn_activate_test": {
        "en": "▶️ Activate Free Test",
        "es": "▶️ Activar Prueba Gratis",
        "pt": "▶️ Ativar Teste Grátis",
    },
    "btn_new_signal": {
        "en": "🔄 New Signal",
        "es": "🔄 Nueva Señal",
        "pt": "🔄 Novo Sinal",
    },
    "btn_menu": {
        "en": "🏠 Menu",
        "es": "🏠 Menú",
        "pt": "🏠 Menu",
    },
}


def create_new_button_messages(apps, schema_editor):
    Bot = apps.get_model("bot", "Bot")
    Message = apps.get_model("bot", "Message")

    for bot in Bot.objects.all():
        for method, translations in NEW_BUTTONS.items():
            for language, text in translations.items():
                Message.objects.get_or_create(
                    bot=bot,
                    method=method,
                    language=language,
                    defaults={"text": text},
                )


def reverse_new_button_messages(apps, schema_editor):
    # при откате не удаляем — могут быть пользовательские правки
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("bot", "0005_default_button_messages"),
    ]

    operations = [
        migrations.RunPython(
            create_new_button_messages,
            reverse_new_button_messages,
        ),
    ]
