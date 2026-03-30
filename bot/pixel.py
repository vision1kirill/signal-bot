"""
facebook pixel (server-side conversions api).
отправляет события напрямую с сервера — без браузера.
документация: https://developers.facebook.com/docs/marketing-api/conversions-api
"""

import hashlib
import time
import logging
import requests

logger = logging.getLogger(__name__)

# базовый url facebook graph api
FB_API_VERSION = "v20.0"
FB_API_URL = "https://graph.facebook.com/{version}/{pixel_id}/events"


def _hash_value(value: str) -> str:
    """sha-256 хэш строки — требование facebook для пользовательских данных."""
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()


def send_pixel_event(
    pixel_id: str,
    access_token: str,
    event_name: str,
    telegram_chat_id: str,
    event_value: float = None,
    currency: str = "USD",
    event_id: str = None,
) -> bool:
    """
    отправляет одно событие в facebook conversions api.

    аргументы:
        pixel_id       — id пикселя из настроек бота
        access_token   — api token из настроек бота
        event_name     — название события (Lead, Purchase, CompleteRegistration)
        telegram_chat_id — telegram id пользователя (используется как external_id)
        event_value    — сумма в долларах (для purchase)
        currency       — валюта (default usd)
        event_id       — дедупликация событий (опционально)

    возвращает True при успехе, False при ошибке.
    """
    if not pixel_id or not access_token:
        # пиксель не настроен — пропускаем без ошибки
        return False

    url = FB_API_URL.format(version=FB_API_VERSION, pixel_id=pixel_id)

    # хэшируем telegram id как внешний идентификатор пользователя
    external_id_hash = _hash_value(str(telegram_chat_id))

    event_data = {
        "event_name": event_name,
        "event_time": int(time.time()),
        "action_source": "system_generated",
        "user_data": {
            "external_id": [external_id_hash],
        },
    }

    # добавляем данные о покупке если переданы
    if event_value is not None:
        event_data["custom_data"] = {
            "value": float(event_value),
            "currency": currency,
        }

    if event_id:
        event_data["event_id"] = str(event_id)

    payload = {
        "data": [event_data],
        "access_token": access_token,
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            logger.info(
                "pixel event '%s' отправлен для chat_id=%s", event_name, telegram_chat_id
            )
            return True
        else:
            logger.warning(
                "pixel event '%s' вернул статус %s: %s",
                event_name, response.status_code, response.text
            )
            return False
    except requests.RequestException as e:
        logger.error("ошибка отправки pixel event '%s': %s", event_name, e)
        return False


def send_lead_event(bot_instance, telegram_chat_id: str) -> bool:
    """
    событие Lead — регистрация пользователя на платформе.
    вызывается при получении постбэка о регистрации.
    """
    return send_pixel_event(
        pixel_id=bot_instance.pixel_id,
        access_token=bot_instance.pixel_token,
        event_name="Lead",
        telegram_chat_id=telegram_chat_id,
        event_id=f"lead_{telegram_chat_id}",
    )


def send_purchase_event(
    bot_instance, telegram_chat_id: str, amount: float
) -> bool:
    """
    событие Purchase — внесение депозита (ftd).
    вызывается при получении постбэка о депозите.
    """
    return send_pixel_event(
        pixel_id=bot_instance.pixel_id,
        access_token=bot_instance.pixel_token,
        event_name="Purchase",
        telegram_chat_id=telegram_chat_id,
        event_value=amount,
        currency="USD",
        event_id=f"purchase_{telegram_chat_id}",
    )


def send_complete_registration_event(bot_instance, telegram_chat_id: str) -> bool:
    """
    событие CompleteRegistration — пользователь получил полный доступ.
    вызывается при автовыдаче полного доступа после депозита.
    """
    return send_pixel_event(
        pixel_id=bot_instance.pixel_id,
        access_token=bot_instance.pixel_token,
        event_name="CompleteRegistration",
        telegram_chat_id=telegram_chat_id,
        event_id=f"complete_reg_{telegram_chat_id}",
    )
