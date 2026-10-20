"""Academy time. Timestamps are stored as naive UTC; calendar days are the academy's local
days (Kuwait by default, ``DOJO_TIMEZONE``)."""

from datetime import UTC, date, datetime, time, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

from app.core.config import get_settings


@lru_cache
def academy_tz() -> ZoneInfo:
    return ZoneInfo(get_settings().timezone)


def today() -> date:
    """The current calendar date at the academy."""
    return datetime.now(academy_tz()).date()


def to_utc_naive(value: datetime) -> datetime:
    """Normalise an incoming timestamp for storage. Naive values are academy local time."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=academy_tz())
    return value.astimezone(UTC).replace(tzinfo=None)


def to_local(value: datetime) -> datetime:
    """A stored timestamp (naive UTC, or aware) as an aware academy-local datetime."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(academy_tz())


def day_range_utc(first: date, last: date | None = None) -> tuple[datetime, datetime]:
    """Half-open UTC range [start, end) covering academy days ``first`` .. ``last``."""
    last = last or first
    tz = academy_tz()
    start = datetime.combine(first, time.min, tzinfo=tz)
    end = datetime.combine(last + timedelta(days=1), time.min, tzinfo=tz)
    return to_utc_naive(start), to_utc_naive(end)
