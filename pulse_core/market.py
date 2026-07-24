"""
Pulse Core — Market definitions and trading hours.
Shared between selfhosted (n200) and cloud (Render) versions.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

MARKETS = {
    "US":  {"tz": "America/New_York", "open": (9, 30), "close": (16, 0)},
    "HK":  {"tz": "Asia/Hong_Kong",   "open": (9, 30), "close": (16, 0), "lunch": ((12, 0), (13, 0))},
    "CN":  {"tz": "Asia/Shanghai",    "open": (9, 30), "close": (15, 0), "lunch": ((11, 30), (13, 0))},
    "TW":  {"tz": "Asia/Taipei",      "open": (9, 0),  "close": (13, 30)},
    "TWO": {"tz": "Asia/Taipei",      "open": (9, 0),  "close": (13, 30)},
}

MARKET_ORDER = {"US": 0, "HK": 1, "CN": 2, "TW": 3, "TWO": 4}


def is_market_open(key: str) -> bool:
    m = MARKETS.get(key)
    if not m:
        return False
    now = datetime.now(ZoneInfo(m["tz"]))
    if now.weekday() >= 5:
        return False
    minutes = now.hour * 60 + now.minute
    open_m  = m["open"][0] * 60 + m["open"][1]
    close_m = m["close"][0] * 60 + m["close"][1]
    if "lunch" in m:
        l_start = m["lunch"][0][0] * 60 + m["lunch"][0][1]
        l_end   = m["lunch"][1][0] * 60 + m["lunch"][1][1]
        if l_start <= minutes < l_end:
            return False
    return open_m <= minutes <= close_m


def check_any_market_active() -> bool:
    return any(is_market_open(m) for m in ["US", "HK", "CN", "TW", "TWO"])


def check_us_market_active_hours() -> bool:
    return is_market_open("US")
