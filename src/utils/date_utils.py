"""Date and time helpers."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def parse_cli_date(raw: str) -> date:
    """Parse YYYY_M_D format (e.g. 2021_9_1)."""
    try:
        year_s, month_s, day_s = raw.strip().split("_")
        return date(int(year_s), int(month_s), int(day_s))
    except Exception as exc:  # pragma: no cover - unified error mapping
        raise ValueError(f"Invalid date format '{raw}', expected YYYY_M_D") from exc


def parse_x_created_at(raw: str) -> datetime:
    """Parse X created_at timestamp and normalize to UTC."""
    return datetime.strptime(raw, "%a %b %d %H:%M:%S %z %Y").astimezone(timezone.utc)


def to_local_date(ts_utc: datetime, timezone_name: str) -> date:
    """Convert UTC timestamp to local date."""
    try:
        tz = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        if timezone_name == "Asia/Shanghai":
            tz = timezone(timedelta(hours=8))
        else:  # pragma: no cover - exercised only for unsupported runtime zones
            raise
    return ts_utc.astimezone(tz).date()


def in_date_range(ts_utc: datetime, start: date, end: date, timezone_name: str) -> bool:
    """Inclusive date range check in local timezone."""
    local_day = to_local_date(ts_utc, timezone_name)
    return start <= local_day <= end
