"""Source UTC days and Shanghai execution days; never a second budget clock."""

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.core.config import settings

ZONE = ZoneInfo("Asia/Shanghai")


def instant(now: datetime | None = None) -> datetime:
    value = now or datetime.now(UTC)
    if value.tzinfo is None:
        raise ValueError("trending_time_requires_timezone")
    return value.astimezone(UTC)


def source_period(source_date: str) -> dict:
    start = datetime.strptime(source_date, "%Y-%m-%d").replace(tzinfo=UTC)
    end = start + timedelta(days=1)
    return {
        "sourceDate": source_date,
        "startAt": start.isoformat(),
        "endAt": end.isoformat(),
        "readyAt": (end + timedelta(minutes=settings.RARDAR_BOARD_READINESS_MINUTES)).isoformat(),
    }


def due_period(now: datetime | None = None) -> dict:
    value = instant(now) - timedelta(minutes=settings.RARDAR_BOARD_READINESS_MINUTES)
    return source_period((value.date() - timedelta(days=1)).isoformat())


def day_plan(now: datetime | None = None) -> dict:
    local = instant(now).astimezone(ZONE)
    # UTC midnight falls at 08:00 Shanghai. Configured bounds keep both slots
    # in the same Shanghai day, including the maximum compensation delay.
    ended = datetime.combine(local.date(), time(), tzinfo=UTC)
    main = ended + timedelta(minutes=settings.RARDAR_BOARD_READINESS_MINUTES)
    compensation = main + timedelta(minutes=settings.RARDAR_BOARD_COMPENSATION_DELAY_MINUTES)
    return {
        "runDate": local.date().isoformat(),
        "mainAt": main.isoformat(),
        "compensationAt": compensation.isoformat(),
        "targetSourceDate": (ended.date() - timedelta(days=1)).isoformat(),
        "periodStartAt": (ended - timedelta(days=1)).isoformat(),
        "periodEndAt": ended.isoformat(),
    }


def schedule_plan(now: datetime | None = None, days: int = 3) -> list[dict]:
    value = instant(now)
    plan = day_plan(value)
    if value >= datetime.fromisoformat(plan["mainAt"]):
        value += timedelta(days=1)
    return [day_plan(value + timedelta(days=offset)) for offset in range(days)]


def policy_status(now: datetime | None = None) -> dict:
    return {
        "timezone": "Asia/Shanghai",
        "readinessMinutes": settings.RARDAR_BOARD_READINESS_MINUTES,
        "compensationDelayMinutes": settings.RARDAR_BOARD_COMPENSATION_DELAY_MINUTES,
        "timingBasis": "provisional_safety_margin",
        "duePeriod": due_period(now),
        "schedule": schedule_plan(now),
    }
