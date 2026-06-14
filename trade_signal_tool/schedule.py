from datetime import datetime, timedelta, timezone
from typing import Iterable


CHINA_TZ = timezone(timedelta(hours=8))


def china_now() -> datetime:
    return datetime.now(CHINA_TZ)


def is_after_close_window(now: datetime, utc_offset_hours: int = 8, close_hour: int = 15, close_minute: int = 5) -> bool:
    local = now.astimezone(timezone(timedelta(hours=utc_offset_hours)))
    close_time = local.replace(hour=close_hour, minute=close_minute, second=0, microsecond=0)
    return local >= close_time


def is_trading_day(yyyymmdd: str, trading_days: Iterable[str]) -> bool:
    return yyyymmdd in set(trading_days)


def weekday_trading_day_fallback(now: datetime) -> bool:
    return now.astimezone(CHINA_TZ).weekday() < 5
