"""
настройки django admin для управления ботами и данными crm.
"""

import copy
from django.contrib import admin
from django.urls import path
from django.http import HttpResponseRedirect
from django.utils.translation import gettext_lazy as _
from django.db import transaction
from django.db.models import Count

from bot.models import (
    Bot, Image, Message, Link, Postback, BotAccess,
    TempAccess, MultiChat, User, BotMarketing, CustomSignal, Channel
)
from crm.models import Market, Pair, Expiration
from bot.utils import start_bot, stop_bot, active_bots

import logging
logger = logging.getLogger(__name__)


# =========================================================
# дефолтные тексты кнопок (синхронизированы с bot/bot.py get_btn defaults)
# =========================================================

_DEFAULT_BUTTON_MESSAGES = {
    "btn_start":    {"en": "▶️ Start Bot",        "es": "▶️ Iniciar Bot",          "pt": "▶️ Iniciar Bot"},
    "btn_activate": {"en": "🚀 Activate Bot",      "es": "🚀 Activar Bot",           "pt": "🚀 Ativar Bot"},
    "btn_free_test":{"en": "🆓 Free Test",         "es": "🆓 Prueba Gratis",         "pt": "🆓 Teste Grátis"},
    "btn_signal":   {"en": "📊 Get Signal",        "es": "📊 Obtener Señal",         "pt": "📊 Obter Sinal"},
    "btn_reviews":  {"en": "⭐ Reviews",           "es": "⭐ Reseñas",               "pt": "⭐ Avaliações"},
    "btn_support":  {"en": "💬 Support",           "es": "💬 Soporte",               "pt": "💬 Suporte"},
    "btn_about":    {"en": "ℹ️ About Us",          "es": "ℹ️ Sobre Nosotros",        "pt": "ℹ️ Sobre Nós"},
    "btn_language": {"en": "🌍 Language",          "es": "🌍 Idioma",                "pt": "🌍 Idioma"},
    "btn_back":     {"en": "◀️ Back",              "es": "◀️ Atrás",                 "pt": "◀️ Voltar"},
    "btn_retry":    {"en": "🔄 Try Again",         "es": "🔄 Intentar de Nuevo",     "pt": "🔄 Tentar Novamente"},
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


def _create_default_button_messages(bot_obj):
    """создаёт дефолтные записи кнопок для бота если их ещё нет."""
    for method, translations in _DEFAULT_BUTTON_MESSAGES.items():
        for language, text in translations.items():
            Message.objects.get_or_create(
                bot=bot_obj, method=method, language=language,
                defaults={"text": text},
            )


# =========================================================
# inline-классы для вложенного редактирования
# =========================================================

class ImageInline(admin.TabularInline):
    model = Image
    extra = 0
    fields = ("name", "image")
    classes = ("collapse",)


class MessageInline(admin.TabularInline):
    """сообщения с поддержкой языков — группируем по методу."""
    model = Message
    extra = 0
    fields = ("method", "language", "text", "image")
    classes = ("collapse",)
    ordering = ("method", "language")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        field = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name == "image":
            bot_id = request.resolver_match.kwargs.get("object_id")
            if bot_id:
                field.queryset = Image.objects.filter(bot_id=bot_id)
            else:
                field.queryset = Image.objects.none()
        return field


class LinkInline(admin.TabularInline):
    model = Link
    extra = 0
    fields = ("name", "method", "url")
    classes = ("collapse",)


class BotAccessInline(admin.TabularInline):
    model = BotAccess
    extra = 0
    fields = ("chat_id",)
    classes = ("collapse",)
    readonly_fields = ("chat_id",)


class TempAccessInline(admin.TabularInline):
    model = TempAccess
    extra = 0
    fields = ("chat_id", "created_at")
    readonly_fields = ("chat_id", "created_at")
    classes = ("collapse",)


class MultiChatInline(admin.TabularInline):
    model = MultiChat
    extra = 0
    fields = ("channel_id",)
    classes = ("collapse",)


class UserInline(admin.TabularInline):
    model = User
    extra = 0
    fields = ("chat_id", "username", "language", "topic_id")
    readonly_fields = ("chat_id", "username", "topic_id")
    classes = ("collapse",)


class BotMarketingInline(admin.TabularInline):
    """рассылка — при сохранении запускается send_marketing."""
    model = BotMarketing
    extra = 1
    max_num = 1
    fields = ("segment", "language_filter", "text", "image", "scheduled_at")
    classes = ("collapse",)

    def get_queryset(self, request):
        # показываем пустую форму — рассылки не накапливаются
        return BotMarketing.objects.none()


class CustomSignalInline(admin.TabularInline):
    model = CustomSignal
    extra = 0
    max_num = 20
    fields = ("chat_id", "order", "direction")
    classes = ("collapse",)


class ChannelInline(admin.TabularInline):
    model = Channel
    extra = 0
    fields = ("name", "method", "channel_id")
    classes = ("collapse",)


# =========================================================
# admin: Message — отдельный раздел с фильтром по языку
# =========================================================

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    """отдельный раздел для удобного редактирования сообщений по языкам."""
    list_display  = ("method", "language", "bot", "text_preview")
    list_filter   = ("bot", "language")
    search_fields = ("method", "text")
    ordering      = ("bot", "method", "language")
    fields        = ("bot", "method", "language", "text", "image")

    def text_preview(self, obj):
        return (obj.text or "—")[:80]
    text_preview.short_description = "Текст (начало)"

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        field = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name == "image":
            obj_id = request.resolver_match.kwargs.get("object_id")
            if obj_id:
                try:
                    msg = Message.objects.get(pk=obj_id)
                    field.queryset = Image.objects.filter(bot=msg.bot)
                except Message.DoesNotExist:
                    pass
        return field


# =========================================================
# admin: Bot
# =========================================================

@admin.register(Bot)
class BotAdmin(admin.ModelAdmin):
    list_display = (
        "name", "platform", "is_active", "min_deposit",
        "users_count", "temp_access_count", "bot_access_count",
        "pixel_configured",
    )
    list_filter = ("is_active", "platform")
    search_fields = ("name", "token")
    fields = (
        "name", "token", "platform", "min_deposit", "ref_id",
        "api_partner_id", "api_key",
        "pixel_id", "pixel_token",
    )
    inlines = [
        ImageInline,
        MessageInline,
        LinkInline,
        BotAccessInline,
        TempAccessInline,
        MultiChatInline,
        UserInline,
        BotMarketingInline,
        CustomSignalInline,
        ChannelInline,
    ]
    actions = ["duplicate"]
    change_form_template = "admin/bot/bot/change_form.html"

    # --- статистические поля ---

    def users_count(self, obj):
        return User.objects.filter(bot=obj).count()
    users_count.short_description = "👥 Пользователи"

    def temp_access_count(self, obj):
        return TempAccess.objects.filter(bot=obj).count()
    temp_access_count.short_description = "⏳ Тест"

    def bot_access_count(self, obj):
        return BotAccess.objects.filter(bot=obj).count()
    bot_access_count.short_description = "✅ Полный доступ"

    def pixel_configured(self, obj):
        return bool(obj.pixel_id and obj.pixel_token)
    pixel_configured.boolean = True
    pixel_configured.short_description = "🎯 Pixel"

    # --- дублирование бота ---

    @admin.action(description=_("📋 Скопировать бота"))
    @transaction.atomic
    def duplicate(self, request, queryset):
        """создаёт копию бота с сообщениями и ссылками."""
        for obj in queryset:
            obj_copy = copy.copy(obj)
            obj_copy.id = None
            obj_copy.name = f"{obj_copy.name} (копия)"
            obj_copy.is_active = False
            obj_copy.save()

            # копируем изображения
            image_map = {}
            for image_obj in Image.objects.filter(bot=obj):
                new_img = Image.objects.create(
                    bot=obj_copy,
                    name=image_obj.name,
                    image=image_obj.image,
                )
                image_map[image_obj.id] = new_img

            # копируем сообщения для всех языков
            for msg in Message.objects.filter(bot=obj):
                new_image = image_map.get(msg.image_id) if msg.image_id else None
                Message.objects.get_or_create(
                    bot=obj_copy,
                    method=msg.method,
                    language=msg.language,
                    defaults={"text": msg.text, "image": new_image},
                )

            # копируем ссылки
            for link in Link.objects.filter(bot=obj):
                Link.objects.get_or_create(
                    bot=obj_copy,
                    method=link.method,
                    defaults={"name": link.name, "url": link.url},
                )

            # копируем каналы
            for channel in Channel.objects.filter(bot=obj):
                Channel.objects.get_or_create(
                    bot=obj_copy,
                    method=channel.method,
                    defaults={"name": channel.name, "channel_id": ""},
                )

        self.message_user(request, f"Скопировано ботов: {queryset.count()}")

    # --- создаём дефолтные записи кнопок при сохранении нового бота ---

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            # новый бот — создаём дефолтные сообщения для кнопок
            _create_default_button_messages(obj)

    # --- скрываем инлайны при создании нового бота ---

    def get_inline_instances(self, request, obj=None):
        if not obj:
            return []
        return super().get_inline_instances(request, obj)

    # --- кастомные url для кнопки запуск/стоп ---

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:bot_id>/toggle/",
                self.admin_site.admin_view(self.toggle_bot),
                name="bot_toggle",
            ),
        ]
        return custom_urls + urls

    def change_view(self, request, object_id, form_url="", extra_context=None):
        """передаём в шаблон реальный статус бота из active_bots."""
        extra_context = extra_context or {}
        try:
            bot_id = int(object_id)
            extra_context["bot_is_running"] = bot_id in active_bots
        except (TypeError, ValueError):
            extra_context["bot_is_running"] = False
        return super().change_view(request, object_id, form_url, extra_context)

    def toggle_bot(self, request, bot_id):
        """включает или выключает бота."""
        try:
            bot = Bot.objects.get(pk=bot_id)
        except Bot.DoesNotExist:
            self.message_user(request, "Бот не найден!", level="error")
            return HttpResponseRedirect(request.META.get("HTTP_REFERER", "/admin/"))

        # проверяем реальный статус по active_bots — не по БД
        is_running = bot_id in active_bots
        if not is_running:
            start_bot(bot)
        else:
            stop_bot(bot)

        now_running = bot_id in active_bots
        self.message_user(
            request,
            f"Бот {bot.name} теперь {'🟢 запущен' if now_running else '🔴 остановлен'}",
        )
        return HttpResponseRedirect(request.META.get("HTTP_REFERER", "/admin/"))


# =========================================================
# admin: Market, Pair, Expiration
# =========================================================

@admin.register(Market)
class MarketAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    search_fields = ("name",)


@admin.register(Pair)
class PairAdmin(admin.ModelAdmin):
    list_display = ("id", "symbol", "market", "price")
    list_filter = ("market",)
    search_fields = ("symbol",)
    list_editable = ("price",)


@admin.register(Expiration)
class ExpirationAdmin(admin.ModelAdmin):
    list_display = ("id", "label")
    search_fields = ("label",)


# =========================================================
# admin: Postback — логирование постбэков
# =========================================================

@admin.register(Postback)
class PostbackAdmin(admin.ModelAdmin):
    list_display = (
        "bot", "user_id", "telegram_username", "chat_id", "link_id",
        "deposit", "deposit_amount", "created_at", "deposited_at",
    )
    list_filter = ("bot", "link_id", "deposit")
    search_fields = ("user_id", "chat_id", "link_id")
    readonly_fields = ("created_at", "deposited_at")
    ordering = ("-created_at",)

    def telegram_username(self, obj):
        """имя пользователя telegram по chat_id из постбэка."""
        if not obj.chat_id:
            return "—"
        user = User.objects.filter(bot=obj.bot, chat_id=obj.chat_id).first()
        if user and user.username:
            return f"@{user.username}"
        return "—"
    telegram_username.short_description = "Telegram"


# =========================================================
# admin: User — управление пользователями
# =========================================================

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("chat_id", "username", "platform_user_id", "bot", "language", "access_status")
    list_filter = ("bot", "language")
    search_fields = ("chat_id", "username")
    readonly_fields = ("chat_id", "username", "topic_id")
    ordering = ("bot", "chat_id")

    def platform_user_id(self, obj):
        """id пользователя на платформе из постбэка."""
        postback = Postback.objects.filter(
            bot=obj.bot, chat_id=obj.chat_id
        ).exclude(user_id="").order_by("-created_at").first()
        return postback.user_id if postback else "—"
    platform_user_id.short_description = "ID платформы"

    def access_status(self, obj):
        """показывает статус доступа пользователя."""
        if BotAccess.objects.filter(bot=obj.bot, chat_id=obj.chat_id).exists():
            return "✅ Полный"
        if TempAccess.objects.filter(bot=obj.bot, chat_id=obj.chat_id).exists():
            return "⏳ Тест"
        return "❌ Нет"
    access_status.short_description = "Доступ"

    actions = ["grant_full_access"]

    @admin.action(description="✅ Выдать полный доступ")
    def grant_full_access(self, request, queryset):
        """ручная выдача полного доступа выбранным пользователям."""
        count = 0
        for user_obj in queryset:
            _, created = BotAccess.objects.get_or_create(
                bot=user_obj.bot,
                chat_id=user_obj.chat_id,
            )
            if created:
                count += 1
        self.message_user(
            request, f"Выдан полный доступ: {count} пользователям."
        )


# =========================================================
# admin: BotAccess — ручное управление доступом
# =========================================================

@admin.register(BotAccess)
class BotAccessAdmin(admin.ModelAdmin):
    list_display = ("chat_id", "bot")
    list_filter = ("bot",)
    search_fields = ("chat_id",)
