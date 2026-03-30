from django.db import models


# доступные языки бота
LANGUAGE_CHOICES = [
    ("en", "English 🇬🇧"),
    ("es", "Español 🇪🇸"),
    ("pt", "Português 🇵🇹"),
]


class Bot(models.Model):
    name = models.CharField(max_length=100, verbose_name="Название")
    token = models.CharField(max_length=255, verbose_name="Токен")
    is_active = models.BooleanField(default=False, verbose_name="Активность")
    # минимальный депозит для автовыдачи полного доступа
    min_deposit = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        verbose_name="Минимальный депозит ($)"
    )
    # id реферальной/партнёрской ссылки — используется при линковке id платформы
    # если не задан — id пытается извлечься из url ссылки method=ref
    ref_id = models.CharField(
        max_length=100, blank=True, default="",
        verbose_name="ID реферальной ссылки (lid / aff_id)"
    )
    # facebook pixel — server-side conversions api
    pixel_id = models.CharField(
        max_length=100, blank=True, default="",
        verbose_name="Facebook Pixel ID"
    )
    pixel_token = models.CharField(
        max_length=500, blank=True, default="",
        verbose_name="Facebook Pixel API Token"
    )

    class Meta:
        verbose_name = "Бот"
        verbose_name_plural = "Боты"

    def __str__(self):
        return self.name


class Image(models.Model):
    bot = models.ForeignKey(Bot, on_delete=models.CASCADE)
    name = models.CharField(max_length=200, verbose_name="Название")
    image = models.ImageField(upload_to="telegram_images/", verbose_name="Изображение")

    class Meta:
        verbose_name = "Изображение"
        verbose_name_plural = "Изображения"

    def __str__(self):
        return self.name


class Message(models.Model):
    bot = models.ForeignKey(Bot, on_delete=models.CASCADE)
    method = models.CharField(max_length=100, verbose_name="Кодовое имя")
    # язык сообщения — один метод создаётся для каждого языка
    language = models.CharField(
        max_length=10, choices=LANGUAGE_CHOICES, default="en",
        verbose_name="Язык"
    )
    text = models.TextField(blank=True, null=True, verbose_name="Текст сообщения")
    image = models.ForeignKey(
        Image, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="messages", verbose_name="Изображение"
    )

    class Meta:
        verbose_name = "Сообщение"
        verbose_name_plural = "Сообщения"
        # исключаем дубликаты одного метода на один язык одного бота
        unique_together = [("bot", "method", "language")]

    def __str__(self):
        return f"{self.method} [{self.language}]"


class Link(models.Model):
    bot = models.ForeignKey(Bot, on_delete=models.CASCADE)
    name = models.CharField(max_length=200, verbose_name="Название")
    method = models.CharField(max_length=100, verbose_name="Кодовое имя")
    url = models.URLField(max_length=500, verbose_name="Ссылка")

    class Meta:
        verbose_name = "Ссылка"
        verbose_name_plural = "Ссылки"

    def __str__(self):
        return self.name


class Postback(models.Model):
    bot = models.ForeignKey(
        Bot, on_delete=models.CASCADE, default=None, null=True, blank=True
    )
    chat_id = models.CharField(
        max_length=100, verbose_name="ID телеграмма", blank=True, default=""
    )
    user_id = models.CharField(max_length=100, verbose_name="ID пользователя на платформе")
    link_id = models.CharField(max_length=100, verbose_name="ID реферальной ссылки")
    deposit = models.BooleanField(default=False, verbose_name="Депозит совершён")
    # сумма депозита — сохраняется из ftd-постбэка
    deposit_amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name="Сумма депозита ($)"
    )
    # дата события — для логирования по тз
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата регистрации")
    deposited_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Дата депозита"
    )

    class Meta:
        verbose_name = "Постбэк"
        verbose_name_plural = "Постбэки"
        # один платформенный аккаунт — один telegram-пользователь
        unique_together = [("user_id", "link_id")]

    def __str__(self):
        return f"{self.user_id} (lid={self.link_id})"


class BotAccess(models.Model):
    bot = models.ForeignKey(Bot, on_delete=models.CASCADE)
    chat_id = models.CharField(max_length=100, verbose_name="ID телеграмма")

    class Meta:
        verbose_name = "Полный доступ"
        verbose_name_plural = "Полные доступы"
        unique_together = [("bot", "chat_id")]

    def __str__(self):
        return self.chat_id


class TempAccess(models.Model):
    bot = models.ForeignKey("bot.Bot", on_delete=models.CASCADE)
    chat_id = models.CharField(max_length=100, verbose_name="ID телеграмма")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")

    class Meta:
        verbose_name = "Тестовый доступ"
        verbose_name_plural = "Тестовые доступы"
        unique_together = [("bot", "chat_id")]

    def __str__(self):
        return self.chat_id


class MultiChat(models.Model):
    bot = models.ForeignKey(Bot, on_delete=models.CASCADE)
    channel_id = models.CharField(max_length=100, verbose_name="ID супергруппы")

    class Meta:
        verbose_name = "Мультичат"
        verbose_name_plural = "Мультичаты"

    def __str__(self):
        return self.channel_id


class User(models.Model):
    bot = models.ForeignKey(Bot, on_delete=models.CASCADE)
    chat_id = models.CharField(max_length=100, verbose_name="ID телеграмма")
    topic_id = models.CharField(
        max_length=100, verbose_name="ID топика",
        null=True, blank=True, default=None
    )
    # язык пользователя — определяется автоматически или выбирается вручную
    language = models.CharField(
        max_length=10, choices=LANGUAGE_CHOICES, default="en",
        verbose_name="Язык"
    )
    # username для удобства в админке
    username = models.CharField(
        max_length=100, blank=True, default="", verbose_name="Username"
    )

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"
        unique_together = [("bot", "chat_id")]

    def __str__(self):
        return f"@{self.username} ({self.chat_id})" if self.username else self.chat_id


class BotMarketing(models.Model):
    # сегмент рассылки — по группам пользователей
    SEGMENT_CHOICES = [
        ("all", "Все пользователи"),
        ("no_access", "Без доступа"),
        ("test", "Тестовый доступ"),
        ("full", "Полный доступ"),
    ]
    # фильтр языка — рассылка только определённой языковой аудитории
    LANGUAGE_FILTER_CHOICES = [
        ("all", "Все языки"),
        ("en", "English 🇬🇧"),
        ("es", "Español 🇪🇸"),
        ("pt", "Português 🇵🇹"),
    ]

    bot = models.ForeignKey(Bot, on_delete=models.CASCADE)
    text = models.TextField(verbose_name="Текст рассылки")
    image = models.ImageField(
        upload_to="telegram_images/", verbose_name="Изображение", blank=True
    )
    segment = models.CharField(
        max_length=20, choices=SEGMENT_CHOICES, default="all",
        verbose_name="Сегмент аудитории"
    )
    language_filter = models.CharField(
        max_length=10, choices=LANGUAGE_FILTER_CHOICES, default="all",
        verbose_name="Язык аудитории"
    )
    # отложенная отправка: если задано — рассылка уйдёт в указанное время
    scheduled_at = models.DateTimeField(
        null=True, blank=True,
        verbose_name="Запланировать на (оставьте пустым для немедленной отправки)"
    )
    sent = models.BooleanField(default=False, verbose_name="Отправлено")

    class Meta:
        verbose_name = "Рассылка"
        verbose_name_plural = "Рассылки"

    def __str__(self):
        if self.scheduled_at:
            return f"Рассылка #{self.id} [{self.get_segment_display()}] → {self.scheduled_at:%d.%m %H:%M}"
        return f"Рассылка #{self.id} [{self.get_segment_display()}]"


class CustomSignal(models.Model):
    CHOICES = [
        ("higher", "Higher ↑"),
        ("lower", "Lower ↓"),
    ]

    bot = models.ForeignKey(Bot, on_delete=models.CASCADE)
    chat_id = models.CharField(max_length=100, verbose_name="ID телеграмма")
    direction = models.CharField(
        max_length=100, verbose_name="Направление",
        choices=CHOICES, default="higher"
    )
    # порядковый номер сигнала в очереди (1–5)
    # при запросе пользователя берётся сигнал с наименьшим order и удаляется
    order = models.PositiveIntegerField(
        default=1, verbose_name="Порядок (1 = следующий)"
    )

    class Meta:
        verbose_name = "Кастомный сигнал"
        verbose_name_plural = "Кастомные сигналы"
        ordering = ["order"]

    def __str__(self):
        return f"{self.chat_id} — сигнал #{self.order} ({self.direction})"


class Channel(models.Model):
    bot = models.ForeignKey(Bot, on_delete=models.CASCADE)
    name = models.CharField(max_length=200, verbose_name="Название")
    method = models.CharField(max_length=100, verbose_name="Кодовое имя")
    channel_id = models.CharField(
        max_length=100, verbose_name="ID канала", blank=True
    )

    class Meta:
        verbose_name = "Канал"
        verbose_name_plural = "Каналы"

    def __str__(self):
        return self.name
