"""Daily policy backed by AppSetting and the existing durable provider ledger.

Every Rardar network attempt shares the Shanghai calendar-day allowance. The
ledger is independent of worktree/run IDs, and a configured increase takes
effect on the next day (a decrease immediately restricts further reservations).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from contextlib import asynccontextmanager, contextmanager, nullcontext
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.repositories.app_setting_repo import AppSettingRepository
from app.services.llm.provider_budget import (
    DAILY_SCENE_STAGES,
    DAILY_TASK_ID,
    ProviderBudgetError,
    ProviderBudgetLedger,
    atomic,
    combined_budget_execution,
    file_lock,
    plain,
)

SETTING_KEY = "rardar_daily_operations_config"
TIMEZONE = ZoneInfo("Asia/Shanghai")


class ProviderWorkYield(BaseException):
    """Cooperative scheduling, not a provider/content failure or cancellation.

    Like CancelledError this must cross existing broad Exception fallbacks
    without writing failed Profiles or control results. The operation boundary
    explicitly handles it as waiting, with its successful caches preserved.
    """

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass
class WorkSlice:
    max_requests: int
    background: bool
    started_day: str
    used_requests: int = 0
    code: str | None = None


_work_slice: ContextVar[WorkSlice | None] = ContextVar("rardar_work_slice", default=None)


@contextmanager
def work_slice(max_requests: int = 6, *, background: bool = True):
    if isinstance(max_requests, bool) or not isinstance(max_requests, int) or max_requests < 1:
        raise ValueError("work_slice_limit_invalid")
    if _work_slice.get() is not None:
        raise ValueError("work_slice_nested")
    state = WorkSlice(max_requests, background, calendar_day())
    token = _work_slice.set(state)
    try:
        yield state
    finally:
        _work_slice.reset(token)


def _yield_work(code: str):
    state = _work_slice.get()
    if state is not None:
        state.code = code
    raise ProviderWorkYield(code)


def daily_root() -> Path:
    home = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / ".local" / "state"))
    binding = settings.RARDAR_BUDGET_IDENTITY_DATA_DIR
    data = Path(binding or settings.RARDAR_INTELLIGENCE_DATA_DIR)
    identity = hashlib.sha256(str(data.absolute()).encode()).hexdigest()[:20]
    root = home / "TopicEye" / "daily-provider-budget" / identity
    if binding:
        # A preview must attach to an existing identity, never silently mint
        # a second budget after a typo or a missing runtime directory.
        plain(data)
        plain(root)
        if not data.is_absolute() or not data.is_dir() or not root.is_dir():
            raise ProviderBudgetError("provider_budget_identity_unavailable")
    return root


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


async def configured_execution_policy(db, limit: int) -> dict[str, int]:
    row = await AppSettingRepository(db).get_by_key(SETTING_KEY)
    try:
        config = json.loads(row.value) if row is not None and row.value else {}
        policy = {}
        for key, default in (("interactiveReserve", 10), ("earlyBackgroundLimit", 20)):
            value = config.get(key, min(default, limit))
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= limit:
                raise ValueError
            policy[key] = value
        return policy
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
    policy = (
        await configured_execution_policy(db, limit)
        if limit is not None
        else {
            "interactiveReserve": 0,
            "earlyBackgroundLimit": 0,
        }
    )
    day = calendar_day(now)
    local = (now or datetime.now(UTC)).astimezone(TIMEZONE)
    result = {
        "day": day,
        "timezone": "Asia/Shanghai",
        "configuredLimit": limit,
        "configured": limit is not None,
        **policy,
        "beforeDailyWindow": (local.hour, local.minute) < (8, 30),
    }
    path = daily_root() / day / "provider-budget.json"
    plain(path, missing=True)
    if not path.exists():
        return {
            **result,
            "reserved": 0,
            "attempted": 0,
            "remaining": limit or 0,
            "backgroundRemaining": max(0, (limit or 0) - policy["interactiveReserve"]),
            "preWindowRemaining": policy["earlyBackgroundLimit"],
            "stageBreakdown": {},
        }
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
        "stageBreakdown": snapshot["stageBreakdown"],
        "backgroundRemaining": max(0, ledger.reservation_limit - policy["interactiveReserve"] - snapshot["reserved"]),
        "preWindowRemaining": max(0, policy["earlyBackgroundLimit"] - snapshot["reserved"]),
    }


async def daily_execution_budget(scene: str) -> tuple[ProviderBudgetLedger, str] | None:
    if not scene.startswith("rardar_") or not getattr(settings, "RARDAR_DAILY_OPERATIONS_ENABLED", False):
        return None
    from app.core.database import async_session

    async with async_session() as db:
        limit = await configured_limit(db)
        policy = await configured_execution_policy(db, limit) if limit is not None else None
    if limit is None:
        raise ProviderBudgetError("provider_daily_budget_unconfigured")
    if scene not in DAILY_SCENE_STAGES:
        raise ProviderBudgetError("provider_budget_scene_forbidden")
    ledger = daily_ledger(limit)
    ledger.interactive_reserve = policy["interactiveReserve"]
    ledger.early_background_limit = policy["earlyBackgroundLimit"]
    return ledger, DAILY_SCENE_STAGES[scene]


@contextmanager
def _interactive_intent(root: Path, duration: float):
    directory = root / "interactive-waiters"
    plain(directory, missing=True)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{uuid4().hex}.json"
    atomic(path, {"expiresAt": time.time() + duration + 30})
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


def _interactive_waiting(root: Path) -> bool:
    directory = root / "interactive-waiters"
    plain(directory, missing=True)
    if not directory.exists():
        return False
    for path in directory.glob("*.json"):
        try:
            plain(path)
            if path.stat().st_size > 1024:
                raise ProviderBudgetError("provider_priority_state_invalid")
            if float(json.loads(path.read_bytes())["expiresAt"]) > time.time():
                return True
        except FileNotFoundError:
            continue  # The owner completed between listing and reading.
        except ProviderBudgetError as exc:
            if exc.code == "provider_budget_missing":
                continue
            raise
        except (KeyError, TypeError, ValueError):
            raise ProviderBudgetError("provider_priority_state_invalid") from None
    return False


def _check_work_policy(ledger: ProviderBudgetLedger, *, background: bool) -> None:
    state = _work_slice.get()
    if state is not None:
        if state.started_day != calendar_day():
            _yield_work("calendar_day_changed")
        if state.used_requests >= state.max_requests:
            _yield_work("work_slice_exhausted")
    if not background:
        return
    snapshot = ledger.snapshot()
    if snapshot["reserved"] >= ledger.reservation_limit:
        _yield_work("daily_budget_exhausted")
    if snapshot["reserved"] >= ledger.reservation_limit - getattr(ledger, "interactive_reserve", 0):
        _yield_work("interactive_budget_reserved")
    local = datetime.now(UTC).astimezone(TIMEZONE)
    if (local.hour, local.minute) < (8, 30) and snapshot["reserved"] >= getattr(
        ledger, "early_background_limit", ledger.limit
    ):
        _yield_work("pre_window_background_limit")
    if _interactive_waiting(ledger.execution_lock.parent):
        _yield_work("interactive_request_waiting")


@asynccontextmanager
async def managed_budget_execution(operation, daily, *, scene: str, wait_seconds: float = 180):
    """Priority and bounded slices around the existing one-request OS lock.

    An in-flight request finishes normally. Find waits asynchronously for that
    request, while the next background dispatch yields before reserving money.
    Neither waiting nor yielding consumes a request or resets a ledger.
    """
    if daily is None:
        with combined_budget_execution(operation, daily):
            yield
        return
    ledger = daily[0]
    # Manual background operations cannot claim interactive priority by omitting
    # the scheduler context. Only the existing Find scene is interactive.
    background = scene != "rardar_find_project_comparison"
    state = _work_slice.get()
    if state is not None:
        background = background or state.background
    deadline = time.monotonic() + wait_seconds
    intent = _interactive_intent(ledger.execution_lock.parent, wait_seconds) if not background else nullcontext()
    with intent:
        while True:
            _check_work_policy(ledger, background=background)
            scope = combined_budget_execution(
                operation,
                daily,
                before_reserve=lambda current=ledger: _check_work_policy(current, background=background),
            )
            try:
                scope.__enter__()
            except ProviderBudgetError as exc:
                if exc.code != "provider_budget_busy":
                    raise
                if background:
                    _yield_work("provider_request_busy")
                if time.monotonic() >= deadline:
                    raise
                await asyncio.sleep(0.05)
                if ledger.run_id != f"daily-{calendar_day()}":
                    daily = await daily_execution_budget(scene)
                    ledger = daily[0]
                continue
            break
        if state is not None:
            state.used_requests += 1
        try:
            yield
        except BaseException as exc:
            scope.__exit__(type(exc), exc, exc.__traceback__)
            raise
        else:
            scope.__exit__(None, None, None)
