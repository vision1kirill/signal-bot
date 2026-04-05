"""
Клиент API CleverAff (Binarium).
Документация: GET https://cleveraff.com/api/gamers/{gamerId}/
Лимит: 20 запросов в минуту на ключ.

Использование:
    from .cleveraff_api import check_gamer, PLAYER_NOT_FOUND
    data = check_gamer("12345678", partner_id="52402", api_key="ключ")
    if data is PLAYER_NOT_FOUND:
        # игрок точно не наш (404) — не смотрим в локальную БД
    elif data is None:
        # временная ошибка API (timeout, 5xx) — можно попробовать локальную БД
    else:
        data["reg"]   # bool — зарегистрирован
        data["dep"]   # bool — сделал депозит
        data["stats"] # dict — детали (ftd_amount, reg_date, sub_id, ...)
"""

import logging
import requests

logger = logging.getLogger(__name__)

CLEVERAFF_API_BASE = "https://cleveraff.com/api"
REQUEST_TIMEOUT = 10  # секунд

# Сентинел: игрок точно не найден (HTTP 404) — не fallback на локальную БД
PLAYER_NOT_FOUND = object()


def check_gamer(gamer_id: str, partner_id: str, api_key: str):
    """
    Запрашивает данные игрока по его ID.

    Возвращает:
        dict            — игрок найден. Ключи: reg (bool), dep (bool), stats (dict).
        PLAYER_NOT_FOUND — HTTP 404: игрок точно не наш (чужая ссылка или noref).
        None            — временная ошибка API (timeout, 5xx, 401).
                          В этом случае можно делать fallback на локальную БД.
    """
    url = f"{CLEVERAFF_API_BASE}/gamers/{gamer_id}/"
    params = {
        "partner_id": partner_id,
        "api_key": api_key,
        "types[]": ["reg", "dep", "stats"],
    }

    try:
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)

        if resp.status_code == 200:
            return resp.json()

        if resp.status_code == 404:
            logger.info(
                "CleverAff API: игрок %s не найден (чужая ссылка или noref)", gamer_id
            )
            return PLAYER_NOT_FOUND

        if resp.status_code == 401:
            logger.error("CleverAff API: неверный api_key или partner_id")
            return None

        logger.warning(
            "CleverAff API: неожиданный статус %s для gamerId=%s: %s",
            resp.status_code, gamer_id, resp.text[:300],
        )
        return None

    except requests.exceptions.Timeout:
        logger.warning("CleverAff API: timeout для gamerId=%s", gamer_id)
        return None

    except Exception as e:
        logger.error("CleverAff API: ошибка запроса для gamerId=%s: %s", gamer_id, e)
        return None
