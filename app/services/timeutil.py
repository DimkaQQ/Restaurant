"""Local-time day boundaries. Orders are stored in UTC; a venue in Almaty
(UTC+5) would otherwise see «сегодня» roll over at 05:00 local — morning
sales landing in yesterday's numbers. All "today"/period windows in reports
go through these helpers so the business day matches the wall clock."""
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from app.config import settings


def local_tz() -> ZoneInfo:
    return ZoneInfo(settings.LOCAL_TZ)


def local_today() -> date:
    return datetime.now(local_tz()).date()


def day_start_utc(day: date | None = None) -> datetime:
    """UTC instant of local midnight for the given local date (default today)."""
    d = day or local_today()
    return datetime.combine(d, time.min, tzinfo=local_tz()).astimezone(timezone.utc)
