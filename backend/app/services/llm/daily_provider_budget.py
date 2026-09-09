"""Daily policy backed by AppSetting and the existing durable provider ledger.

Every Rardar network attempt shares the Shanghai calendar-day allowance. The
ledger is independent of worktree/run IDs, and a configured increase takes
effect on the next day (a decrease immediately restricts further reservations).
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.repositories.app_setting_repo import AppSettingRepository
from app.services.llm.provider_budget import (
    DAILY_TASK_ID,
    ProviderBudgetError,
    ProviderBudgetLedger,
    file_lock,
    plain,
)

SETTING_KEY = "rardar_daily_operations_config"
TIMEZONE = ZoneInfo("Asia/Shanghai")


def daily_root() -> Path:
    home = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / ".local" / "state"))
    identity = hashlib.sha256(str(Path(settings.RARDAR_INTELLIGENCE_DATA_DIR).absolute()).encode()).hexdigest()[:20]
    return home / "TopicEye" / "daily-provider-budget" / identity


def calendar_day(now: datetime | None = None) -> str:
    instant = now or datetime.now(UTC)
    if instant.tzinfo is None:
        raise ProviderBudgetError("provider_budget_date_invalid")
    return instant.astimezone(TIMEZONE).date().isoformat()


async def configured_limit(db) -> int | None:
    row = await AppSettingRepository(db).get_by_key(SETTING_KEY)
    if row is None or not row.value:
        return None
    try:
        config = json.loads(row.value)
        value = config.get("providerRequestLimit")
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 100_000:
            raise ValueError
        return value
    except (TypeError, AttributeError, ValueError):
        raise ProviderBudgetError("provider_daily_config_invalid") from None


def _load_existing(path: Path, day: str, limit: int) -> ProviderBudgetLedger:
    plain(path)
    try:
        registered_limit = json.loads(path.read_bytes())["limit"]
        ledger = ProviderBudgetLedger(path, f"daily-{day}", task_id=DAILY_TASK_ID, limit=registered_limit)
        ledger.snapshot()  # Hash chain and registration, not an untrusted summary.
    except (KeyError, ValueError, TypeError):
        raise ProviderBudgetError("provider_daily_ledger_invalid") from None
    ledger.reservation_limit = min(limit, registered_limit)
    # One network operation across all dates, scenes and application processes.
    ledger.execution_lock = path.parent.parent / "provider-execution.lock"
    return ledger


def daily_ledger(limit: int, *, now: datetime | None = None) -> ProviderBudgetLedger:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100_000:
        raise ProviderBudgetError("provider_daily_config_invalid")
    day = calendar_day(now)
    root = daily_root()
    plain(root, missing=True)
    root.mkdir(parents=True, exist_ok=True)
    path = root / day / "provider-budget.json"
    with file_lock(root / "initialize.lock", blocking=False):
        if not path.exists():
            # initialize rejects partial or conflicting state; never reset it.
            ProviderBudgetLedger.initialize(path, f"daily-{day}", task_id=DAILY_TASK_ID, limit=limit)
        return _load_existing(path, day, limit)


async def daily_budget_status(db, *, now: datetime | None = None) -> dict:
    """Read-only status; polling neither initializes a ledger nor spends budget."""
    limit = await configured_limit(db)
    day = calendar_day(now)
    result = {"day": day, "timezone": "Asia/Shanghai", "configuredLimit": limit, "configured": limit is not None}
    path = daily_root() / day / "provider-budget.json"
    plain(path, missing=True)
    if not path.exists():
        return {**result, "reserved": 0, "attempted": 0, "remaining": limit or 0}
    # A removed setting disables calls but keeps the historic usage visible.
    ledger = _load_existing(path, day, limit or 0)
    snapshot = ledger.snapshot()
    return {
        **result,
        "limit": ledger.limit,
        "effectiveLimit": ledger.reservation_limit,
        "reserved": snapshot["reserved"],
        "attempted": snapshot["attempted"],
        "remaining": max(0, ledger.reservation_limit - snapshot["reserved"]),
        "succeeded": snapshot["succeeded"],
        "failed": snapshot["failed"],
    }


async def daily_execution_budget(scene: str) -> tuple[ProviderBudgetLedger, str] | None:
    if not scene.startswith("rardar_") or not getattr(settings, "RARDAR_DAILY_OPERATIONS_ENABLED", False):
        return None
    from app.core.database import async_session

    async with async_session() as db:
        limit = await configured_limit(db)
    if limit is None:
        raise ProviderBudgetError("provider_daily_budget_unconfigured")
    stages = {
        "rardar_news_quickread": "news_quickread",
        "rardar_project_summary": "profile_translation",
        "rardar_explosion_explanation": "project_profile",
        "rardar_project_profile": "project_profile",
        "rardar_find_project_comparison": "find_project",
        "rardar_worth_seeing_gate": "scope_value",
        "rardar_worth_seeing_meaningful_change": "meaningful_change",
        "rardar_worth_seeing_copy": "user_copy",
    }
    if scene not in stages:
        raise ProviderBudgetError("provider_budget_scene_forbidden")
    return daily_ledger(limit), stages[scene]
