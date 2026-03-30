"""
обработчик постбэков от платформы pocket option.
принимает события о регистрации и депозите (ftd).
"""

import logging
from decimal import Decimal, InvalidOperation

from django.shortcuts import render
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone

from bot.models import Bot, Postback
from bot.utils import send_postback
from bot.pixel import send_lead_event, send_purchase_event

logger = logging.getLogger(__name__)


@csrf_exempt
def postback_view(request):
    """
    принимает get-запросы от платформы с параметрами:
        status=reg  — новая регистрация (uid, lid обязательны)
        status=ftd  — первый депозит     (uid, lid, payout обязательны)

    также поддерживает legacy-формат: параметр ftd вместо status=ftd.
    """
    params = request.GET.dict()
    status = params.get("status", "")
    uid = params.get("uid", "").strip()
    lid = params.get("lid", "").strip()

    if not uid or not lid:
        logger.warning("постбэк без uid или lid: %s", params)
        return HttpResponse(status=400)

    try:
        if status == "reg":
            _handle_registration(uid, lid, params)

        elif status == "ftd" or params.get("ftd"):
            # поддержка обоих форматов: status=ftd и ftd=1
            _handle_deposit(uid, lid, params)

        else:
            logger.warning("постбэк с неизвестным статусом: %s", params)

    except Exception as e:
        logger.error("необработанная ошибка постбэка params=%s: %s", params, e)
        return HttpResponse(status=500)

    return HttpResponse(status=200)


def _handle_registration(uid: str, lid: str, params: dict):
    """
    обрабатывает событие регистрации.
    создаёт запись постбэка и отправляет уведомление в канал и facebook pixel.
    """
    # get_or_create предотвращает дубликаты при повторных постбэках
    postback_obj, created = Postback.objects.get_or_create(
        user_id=uid,
        link_id=lid,
        defaults={"chat_id": ""},
    )

    if created:
        logger.info("регистрация: новый пользователь uid=%s lid=%s", uid, lid)
        # уведомляем telegram-канал о регистрации (передаём бота для фильтрации канала)
        send_postback({**params, "status": "reg"}, bot_instance=postback_obj.bot)

        # facebook pixel lead event — отправляем если chat_id уже известен
        if postback_obj.chat_id and postback_obj.bot:
            _fire_lead_pixel(postback_obj)
    else:
        logger.info("регистрация: uid=%s уже существует, пропускаем", uid)


def _handle_deposit(uid: str, lid: str, params: dict):
    """
    обрабатывает событие первого депозита (ftd).
    обновляет запись постбэка суммой и флагом deposit=True.
    автовыдача полного доступа происходит в bot/signals.py через post_save.
    """
    try:
        postback_obj = Postback.objects.get(user_id=uid, link_id=lid)
    except Postback.DoesNotExist:
        # постбэк о депозите пришёл раньше регистрации — создаём запись
        logger.warning(
            "ftd без предварительной регистрации uid=%s lid=%s, создаём запись",
            uid, lid,
        )
        postback_obj = Postback.objects.create(
            user_id=uid, link_id=lid, chat_id=""
        )
    except Postback.MultipleObjectsReturned:
        # берём первый из дубликатов
        postback_obj = Postback.objects.filter(
            user_id=uid, link_id=lid
        ).first()

    # парсим сумму депозита
    raw_payout = params.get("payout", params.get("amount", "0"))
    deposit_amount = _parse_amount(raw_payout)

    # обновляем данные депозита
    postback_obj.deposit = True
    postback_obj.deposit_amount = deposit_amount
    postback_obj.deposited_at = timezone.now()
    postback_obj.save()

    logger.info(
        "депозит: uid=%s lid=%s сумма=%s", uid, lid, deposit_amount
    )

    # уведомляем telegram-канал о депозите (передаём бота для фильтрации канала)
    send_postback(
        {**params, "status": "ftd", "payout": str(deposit_amount or 0)},
        bot_instance=postback_obj.bot,
    )

    # facebook pixel purchase event
    if postback_obj.chat_id and postback_obj.bot and deposit_amount:
        _fire_purchase_pixel(postback_obj, deposit_amount)


def _parse_amount(raw_value: str):
    """безопасно конвертирует строку в Decimal. возвращает None при ошибке."""
    try:
        cleaned = str(raw_value).replace(",", ".").strip()
        return Decimal(cleaned)
    except (InvalidOperation, ValueError, TypeError):
        logger.warning("не удалось распарсить сумму депозита: '%s'", raw_value)
        return None


def _fire_lead_pixel(postback_obj: Postback):
    """отправляет Lead-событие в facebook pixel для бота из постбэка."""
    try:
        if postback_obj.bot and postback_obj.bot.pixel_id:
            send_lead_event(postback_obj.bot, postback_obj.chat_id)
    except Exception as e:
        logger.warning("ошибка pixel lead event: %s", e)


def _fire_purchase_pixel(postback_obj: Postback, amount: Decimal):
    """отправляет Purchase-событие в facebook pixel для бота из постбэка."""
    try:
        if postback_obj.bot and postback_obj.bot.pixel_id:
            send_purchase_event(postback_obj.bot, postback_obj.chat_id, float(amount))
    except Exception as e:
        logger.warning("ошибка pixel purchase event: %s", e)
