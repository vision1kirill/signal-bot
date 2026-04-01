"""
обработчик постбэков от торговых платформ.

поддерживаемые платформы:
    /postback/          — Pocket Option (обратная совместимость)
    /postback/pocket/   — Pocket Option
    /postback/binarium/ — Binarium / CleverAff

каждый эндпоинт нормализует параметры через crm.postback_adapters
и передаёт их в общие обработчики _handle_registration / _handle_deposit.
"""

import logging
from decimal import Decimal, InvalidOperation

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone

from bot.models import Bot, Postback
from bot.utils import send_postback
from bot.pixel import send_lead_event, send_purchase_event
from .postback_adapters import normalize

logger = logging.getLogger(__name__)


# =========================================================
# публичные эндпоинты
# =========================================================

@csrf_exempt
def postback_view(request):
    """Pocket Option — оригинальный эндпоинт (обратная совместимость)."""
    return _dispatch(request, platform="pocket")


@csrf_exempt
def postback_pocket_view(request):
    """Pocket Option — именованный эндпоинт."""
    return _dispatch(request, platform="pocket")


@csrf_exempt
def postback_binarium_view(request):
    """Binarium / CleverAff — эндпоинт."""
    return _dispatch(request, platform="binarium")


# =========================================================
# диспетчер
# =========================================================

def _dispatch(request, platform: str):
    """
    нормализует параметры запроса под стандартный формат
    и вызывает нужный обработчик.
    """
    params = request.GET.dict()
    data = normalize(platform, params)

    uid = data["uid"]
    lid = data["lid"]
    status = data["status"]

    # uid обязателен всегда; lid может отсутствовать (напр. subid не задан у Binarium)
    if not uid:
        logger.warning("[%s] постбэк без uid: %s", platform, params)
        return HttpResponse(status=400)

    if not lid:
        logger.warning("[%s] постбэк без lid (subid пустой?): uid=%s params=%s", platform, uid, params)

    try:
        if status == "reg":
            _handle_registration(uid, lid, data, platform)
        elif status == "ftd":
            _handle_deposit(uid, lid, data, platform)
        else:
            logger.warning(
                "[%s] постбэк с неизвестным статусом '%s': %s",
                platform, status, params,
            )
    except Exception as e:
        logger.error(
            "[%s] необработанная ошибка uid=%s lid=%s: %s",
            platform, uid, lid, e,
        )
        return HttpResponse(status=500)

    return HttpResponse(status=200)


# =========================================================
# обработчики событий (общие для всех платформ)
# =========================================================

def _handle_registration(uid: str, lid: str, data: dict, platform: str):
    """
    обрабатывает событие регистрации.
    get_or_create предотвращает дубликаты при повторных постбэках.
    """
    postback_obj, created = Postback.objects.get_or_create(
        user_id=uid,
        link_id=lid,
        defaults={"chat_id": ""},
    )

    if created:
        logger.info(
            "[%s] регистрация: новый пользователь uid=%s lid=%s",
            platform, uid, lid,
        )
        send_postback(
            {**data, "status": "reg", "uid": uid, "lid": lid},
            bot_instance=postback_obj.bot,
        )
        if postback_obj.chat_id and postback_obj.bot:
            _fire_lead_pixel(postback_obj)
    else:
        logger.info(
            "[%s] регистрация: uid=%s уже существует, пропускаем",
            platform, uid,
        )


def _handle_deposit(uid: str, lid: str, data: dict, platform: str):
    """
    обрабатывает событие первого депозита (ftd).
    автовыдача доступа срабатывает через post_save сигнал в bot/signals.py.
    """
    try:
        postback_obj = Postback.objects.get(user_id=uid, link_id=lid)
    except Postback.DoesNotExist:
        logger.warning(
            "[%s] ftd без предварительной регистрации uid=%s lid=%s, создаём запись",
            platform, uid, lid,
        )
        postback_obj = Postback.objects.create(
            user_id=uid, link_id=lid, chat_id=""
        )
    except Postback.MultipleObjectsReturned:
        postback_obj = Postback.objects.filter(user_id=uid, link_id=lid).first()

    deposit_amount = _parse_amount(data.get("amount", "0"))

    postback_obj.deposit = True
    postback_obj.deposit_amount = deposit_amount
    postback_obj.deposited_at = timezone.now()
    postback_obj.save()

    logger.info(
        "[%s] депозит: uid=%s lid=%s сумма=%s",
        platform, uid, lid, deposit_amount,
    )

    send_postback(
        {**data, "status": "ftd", "uid": uid, "lid": lid,
         "payout": str(deposit_amount or 0)},
        bot_instance=postback_obj.bot,
    )

    if postback_obj.chat_id and postback_obj.bot and deposit_amount:
        _fire_purchase_pixel(postback_obj, deposit_amount)


# =========================================================
# вспомогательные функции
# =========================================================

def _parse_amount(raw_value: str):
    """безопасно конвертирует строку в Decimal. возвращает None при ошибке."""
    try:
        cleaned = str(raw_value).replace(",", ".").strip()
        return Decimal(cleaned)
    except (InvalidOperation, ValueError, TypeError):
        logger.warning("не удалось распарсить сумму депозита: '%s'", raw_value)
        return None


def _fire_lead_pixel(postback_obj: Postback):
    try:
        if postback_obj.bot and postback_obj.bot.pixel_id:
            send_lead_event(postback_obj.bot, postback_obj.chat_id)
    except Exception as e:
        logger.warning("ошибка pixel lead event: %s", e)


def _fire_purchase_pixel(postback_obj: Postback, amount: Decimal):
    try:
        if postback_obj.bot and postback_obj.bot.pixel_id:
            send_purchase_event(postback_obj.bot, postback_obj.chat_id, float(amount))
    except Exception as e:
        logger.warning("ошибка pixel purchase event: %s", e)
