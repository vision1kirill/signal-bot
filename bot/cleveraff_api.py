"""
Клиент API CleverAff (Binarium).
Документация: GET https://cleveraff.com/api/gamers/{gamerId}/
Лимит: 20 запросов в минуту на ключ.

Использование:
    from .cleveraff_api import check_gamer
    data = check_gamer("12345678", partner_id="52402", api_key="ключ")
    if data is None:
        # игрок не найден (404) или API недоступен
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


def check_gamer(gamer_id: str, partner_id: str, api_key: str) -> dict | None:
    """
    Запрашивает данные игрока по его ID.

    Возвращает:
        dict  — если игрок найден и привязан к нашему партнёру.
                Ключи: reg (bool), dep (bool), stats (dict).
        None  — если игрок не найден (404), не наш, или временная ошибка API.
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
            logger.info("CleverAff API: игрок %s не найден (чужая ссылка или noref)", gamer_id)
            return None

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
