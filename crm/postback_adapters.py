"""
адаптеры постбэков для разных платформ.

каждый адаптер принимает словарь GET-параметров и возвращает
нормализованный dict со стандартными полями:
    uid    — id пользователя на платформе
    lid    — id реферальной ссылки (наш subid/tracking id)
    status — "reg" | "ftd" | ""
    amount — сумма депозита (строка, может быть "0")

добавить новую платформу: создать функцию normalize_<platform>(params)
и зарегистрировать её в ADAPTERS.
"""


def normalize_pocket(params: dict) -> dict:
    """
    Pocket Option.
    постбэк: /postback/?status=reg&uid=<id>&lid=<lid>
              /postback/?status=ftd&uid=<id>&lid=<lid>&payout=<amount>
    также поддерживает legacy: ftd=1 вместо status=ftd.
    """
    uid = params.get("uid", "").strip()
    lid = params.get("lid", "").strip()
    raw_status = params.get("status", "")

    if raw_status == "ftd" or params.get("ftd"):
        status = "ftd"
    elif raw_status == "reg":
        status = "reg"
    else:
        status = raw_status

    amount = params.get("payout", params.get("amount", "0"))
    return {"uid": uid, "lid": lid, "status": status, "amount": amount}


def normalize_binarium(params: dict) -> dict:
    """
    Binarium / CleverAff (https://cleveraff.info/).

    Типовой формат постбэка CleverAff:
        uid   / transaction_id / user_id / trader_id  — id трейдера на платформе
        lid   / click_id / subid / aff_id             — наш subid (id реф. ссылки)
        goal  / type / status / event                 — тип события
            "reg" / "registration" / "lead"     → reg
            "ftd" / "deposit" / "sale"          → ftd
        amount / payout / sum                         — сумма депозита

    Если тестировщик найдёт другие названия параметров — добавляем их сюда.
    """
    # id трейдера на платформе
    uid = (
        params.get("uid")
        or params.get("transaction_id")
        or params.get("user_id")
        or params.get("trader_id")
        or ""
    ).strip()

    # наш subid — то, что мы передали в реф. ссылке
    lid = (
        params.get("lid")
        or params.get("click_id")
        or params.get("subid")
        or params.get("aff_id")
        or ""
    ).strip()

    # тип события
    raw_goal = (
        params.get("goal")
        or params.get("type")
        or params.get("status")
        or params.get("event")
        or ""
    ).lower().strip()

    if raw_goal in ("reg", "registration", "lead"):
        status = "reg"
    elif raw_goal in ("ftd", "deposit", "sale", "purchase"):
        status = "ftd"
    else:
        status = raw_goal

    amount = (
        params.get("amount")
        or params.get("payout")
        or params.get("sum")
        or "0"
    )
    return {"uid": uid, "lid": lid, "status": status, "amount": amount}


# реестр адаптеров: platform_key → функция нормализации
ADAPTERS = {
    "pocket": normalize_pocket,
    "binarium": normalize_binarium,
}


def normalize(platform: str, params: dict) -> dict:
    """возвращает нормализованные параметры для указанной платформы."""
    adapter = ADAPTERS.get(platform, normalize_pocket)
    return adapter(params)
