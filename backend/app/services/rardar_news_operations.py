"""Small local news operation runner; saved results survive browser navigation.

No scheduler, subprocess shell, automatic retry or generic job platform. The
existing OS lock serializes web and CLI writers; abandoned runs are reported
as interrupted, never silently restarted with a fresh budget.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from app.core.config import settings
from app.core.database import async_session
from app.schemas.rardar_news_operations import NewsOperationRequest
from app.services.llm.provider_budget import (
    ProviderBudgetError,
    ProviderBudgetLedger,
    atomic,
    file_lock,
    news_execution_budget,
    plain,
)
from app.services.rardar_hotspot_news import load_hotspot_news, refresh_hotspot_news
from app.services.rardar_news_operation_lock import news_writer, operation_root
from app.services.rardar_news_quickread import QUICK_READ_TASK_ID, enhance_hotspot_news

_tasks: set[asyncio.Task] = set()
TIMEOUT_SECONDS = 1800


def request_limit() -> int:
    limit = settings.RARDAR_NEWS_REQUEST_LIMIT
    if isinstance(limit, bool) or not 1 <= limit <= 100:
        raise ValueError("news_request_limit_invalid")
    return limit


def _read(path: Path) -> dict[str, Any] | None:
    plain(path, missing=True)
    if not path.exists():
        return None
    if path.stat().st_size > 200_000:
        raise ValueError("news_operation_state_invalid")
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError("news_operation_state_invalid")
    return value


def _state_path(identifier: str) -> Path:
    identifier = str(UUID(identifier))
    return operation_root() / identifier / "operation.json"


def get_operation(identifier: str) -> dict[str, Any] | None:
    saved = _read(_state_path(identifier))
    if saved is None or saved["status"] != "running":
        return saved
    # GET only observes liveness. It never resumes a run or updates its ledger.
    active = False
    try:
        with file_lock(operation_root() / "writer.lock", blocking=False):
            pass
    except ProviderBudgetError as exc:
        if exc.code != "provider_budget_busy":
            raise
        active = True
    deadline = datetime.fromisoformat(saved["startedAt"]) + timedelta(seconds=TIMEOUT_SECONDS + 30)
    if not active or datetime.now(UTC) > deadline:
        return {**saved, "status": "interrupted", "errorCode": "news_executor_interrupted"}
    return saved


def latest_operation() -> dict[str, Any] | None:
    latest = _read(operation_root() / "latest-operation.json")
    return get_operation(latest["id"]) if latest else None


async def start_operation(payload: NewsOperationRequest, *, user_id: int) -> dict[str, Any]:
    from app.core.rardar_scope import require_module_execution

    require_module_execution("news")
    root = operation_root()
    root.mkdir(parents=True, exist_ok=True)
    # Short admission lock also records aliases for clicks made during a run.
    with file_lock(root / "admission.lock", blocking=False):
        key = root / f"request-{user_id}-{payload.requestId}.json"
        existing = _read(key)
        if existing:
            if existing["action"] != payload.action:
                raise ValueError("news_request_conflict")
            return get_operation(existing["id"])
        latest = latest_operation()
        if latest and latest["status"] == "running":
            atomic(key, {"id": latest["id"], "action": payload.action})
            return latest
        ready = asyncio.get_running_loop().create_future()
        task = asyncio.create_task(_execute(payload, key, ready))
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)
        return await asyncio.shield(ready)


async def _execute(payload: NewsOperationRequest, key: Path, ready: asyncio.Future) -> None:
    operation: dict[str, Any] | None = None
    state_path: Path | None = None
    try:
        with news_writer():
            async with asyncio.timeout(TIMEOUT_SECONDS):
                async with async_session() as db:
                    page = None
                    if payload.action == "enhance":
                        page, _ = await load_hotspot_news(
                            db,
                            selected_source=payload.source,
                            selected_topic=payload.topic,
                            sort=payload.sort,
                            page=payload.page,
                            page_size=18,
                        )
                    identifier = str(uuid4())
                    state_path = _state_path(identifier)
                    state_path.parent.mkdir()
                    limit = request_limit() if page is not None else 0
                    operation = {
                        "id": identifier,
                        "action": payload.action,
                        "status": "running",
                        "startedAt": datetime.now(UTC).isoformat(),
                        "completedAt": None,
                        "errorCode": None,
                        "itemIds": [item.id for item in page.items] if page else [],
                        "requestLimit": limit,
                        "result": None,
                    }
                    # Persist the operation before initializing a budget. If the
                    # process dies between writes it is interrupted, not retried.
                    atomic(state_path, operation)
                    atomic(key, {"id": identifier, "action": payload.action})
                    atomic(operation_root() / "latest-operation.json", {"id": identifier})
                    ledger = None
                    if page is not None:
                        ledger = ProviderBudgetLedger.initialize(
                            state_path.parent / "provider-budget.json",
                            identifier,
                            task_id=QUICK_READ_TASK_ID,
                            limit=limit,
                        )
                    ready.set_result(dict(operation))
                    if ledger is not None:
                        with news_execution_budget(ledger):
                            result = await enhance_hotspot_news(db, frozen_page=page)
                    else:
                        result = await refresh_hotspot_news(db)
                    operation.update(
                        status="degraded" if result.status == "busy" else result.status,
                        result=result.model_dump(mode="json"),
                        completedAt=datetime.now(UTC).isoformat(),
                    )
                    atomic(state_path, operation)
    except BaseException as exc:
        code = (
            "news_executor_interrupted"
            if isinstance(exc, asyncio.CancelledError | TimeoutError)
            else "news_operation_failed"
        )
        try:
            if operation is not None and state_path is not None:
                operation.update(
                    status="interrupted" if code == "news_executor_interrupted" else "failed",
                    errorCode=code,
                    completedAt=datetime.now(UTC).isoformat(),
                )
                atomic(state_path, operation)
        except OSError:
            # A saved running record becomes interrupted when its OS lock is
            # released. Disk failure must not leave the POST future hanging.
            pass
        finally:
            if not ready.done():
                ready.set_exception(
                    ValueError(
                        "news_writer_busy"
                        if isinstance(exc, ProviderBudgetError) and exc.code == "provider_budget_busy"
                        else code
                    )
                )
        if isinstance(exc, asyncio.CancelledError):
            raise
