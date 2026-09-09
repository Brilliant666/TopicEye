"""Small local Today operation entry using the existing sync and OS-lock primitives."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from contextlib import suppress
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from app.core.config import settings
from app.integrations.rardar.serving import ServingProjectionError, ServingProjectionLoader
from app.integrations.rardar.sync import RardarSyncError, sync_rardar_intelligence
from app.schemas.rardar_today_operations import TodayOperationRequest
from app.services.llm.provider_budget import ProviderBudgetError, atomic, file_lock, plain

_tasks: set[asyncio.Task] = set()


def operation_root() -> Path:
    identity = hashlib.sha256(settings.RARDAR_INTELLIGENCE_DATA_DIR.encode()).hexdigest()[:20]
    home = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / ".local" / "state"))
    root = home / "TopicEye" / "today-operations" / identity
    plain(root, missing=True)
    return root


def _read(path: Path) -> dict[str, Any] | None:
    plain(path, missing=True)
    if not path.exists():
        return None
    if path.stat().st_size > 200_000:
        raise ValueError("today_operation_state_invalid")
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError("today_operation_state_invalid")
    return value


def get_operation(identifier: str) -> dict[str, Any] | None:
    identifier = str(UUID(identifier))
    saved = _read(operation_root() / identifier / "operation.json")
    if not saved or saved["status"] != "running":
        return saved
    latest = _read(operation_root() / "latest-operation.json")
    if not latest or latest.get("id") != identifier:
        return {**saved, "status": "interrupted", "errorCode": "today_executor_interrupted"}
    try:
        with file_lock(operation_root() / "writer.lock", blocking=False):
            pass
    except ProviderBudgetError as exc:
        if exc.code != "provider_budget_busy":
            raise
        return saved
    return {**saved, "status": "interrupted", "errorCode": "today_executor_interrupted"}


def latest_operation() -> dict[str, Any] | None:
    latest = _read(operation_root() / "latest-operation.json")
    return get_operation(latest["id"]) if latest else None


def last_successful_sync_at() -> str | None:
    saved = _read(operation_root() / "last-successful-sync.json")
    return saved.get("completedAt") if saved else None


def _sync():
    # Same collector/build/install path as CLI, with model generation explicitly
    # disabled. Fixed server-side values; no environment mutation per request.
    from scripts.rebuild_rardar_serving import real_profile_provider

    return sync_rardar_intelligence(
        target=Path(settings.RARDAR_INTELLIGENCE_DATA_DIR),
        host=settings.RARDAR_TODAY_SOURCE_HOST,
        remote_root=settings.RARDAR_TODAY_SOURCE_ROOT,
        profile_provider=real_profile_provider(translate_top=20, allow_model_generation=False),
        check_published=True,
    )


async def start_operation(payload: TodayOperationRequest, *, user_id: int) -> dict[str, Any]:
    root = operation_root()
    root.mkdir(parents=True, exist_ok=True)
    with file_lock(root / "admission.lock", blocking=False):
        key = root / f"request-{user_id}-{payload.requestId}.json"
        existing = _read(key)
        if existing:
            return get_operation(existing["id"])
        latest = latest_operation()
        if latest and latest["status"] == "running":
            atomic(key, {"id": latest["id"]})
            return latest
        loop = asyncio.get_running_loop()
        ready = loop.create_future()
        task = asyncio.create_task(asyncio.to_thread(_execute, key, loop, ready))
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)
        return await asyncio.shield(ready)


def _execute(key: Path, loop: asyncio.AbstractEventLoop, ready: asyncio.Future) -> None:
    operation = None
    state_path = None
    announced = False
    try:
        # The thread owns the OS lock throughout sync, including if the HTTP
        # caller disconnects or its await is cancelled. No overlapping writer.
        with file_lock(operation_root() / "writer.lock", blocking=False):
            identifier = str(uuid4())
            state_path = operation_root() / identifier / "operation.json"
            state_path.parent.mkdir()
            operation = {
                "id": identifier,
                "status": "running",
                "startedAt": datetime.now(UTC).isoformat(),
                "completedAt": None,
                "errorCode": None,
                "providerCalls": 0,
                "result": None,
            }
            atomic(state_path, operation)
            atomic(key, {"id": identifier})
            atomic(operation_root() / "latest-operation.json", {"id": identifier})
            loop.call_soon_threadsafe(ready.set_result, dict(operation))
            announced = True
            if not settings.RARDAR_INTELLIGENCE_DATA_DIR:
                raise RardarSyncError("rardar_sync_invalid_configuration", "Not configured")
            result = _sync()
            saved = asdict(result)
            current = None
            try:
                current, _ = ServingProjectionLoader(settings.RARDAR_INTELLIGENCE_DATA_DIR).load_today_with_etag()
            except ServingProjectionError:
                if saved.get("outcome") != "no_complete_board":
                    raise
            operation.update(
                status=saved.get("outcome") or ("updated" if result.changed else "unchanged"),
                completedAt=datetime.now(UTC).isoformat(),
                result={
                    "generationId": current.generationId if current else None,
                    "window": current.window.model_dump(mode="json") if current and current.window else None,
                    "syncedAt": current.syncedAt.isoformat() if current and current.syncedAt else None,
                    "changed": result.changed,
                    "upstreamWindow": saved.get("upstream_window"),
                },
            )
            atomic(state_path, operation)
            if operation["status"] == "updated":
                atomic(
                    operation_root() / "last-successful-sync.json",
                    {
                        "id": identifier,
                        "completedAt": operation["completedAt"],
                    },
                )
    except Exception as exc:
        # Only allowlisted error codes leave the process; never SSH stderr,
        # arbitrary exception text, request bodies or environment values.
        known = {
            "rardar_sync_invalid_configuration",
            "rardar_sync_remote_unavailable",
            "rardar_sync_remote_rejected",
            "rardar_sync_bundle_invalid",
            "rardar_sync_validation_failed",
            "rardar_sync_already_running",
            "rardar_sync_generation_conflict",
            "rardar_sync_unsafe_local_path",
            "rardar_sync_failed",
        }
        code = getattr(exc, "code", None)
        code = code if code in known else "today_operation_failed"
        if operation and state_path:
            operation.update(
                status="not_configured" if code == "rardar_sync_invalid_configuration" else "failed",
                errorCode=code,
                completedAt=datetime.now(UTC).isoformat(),
            )
            # A missing lock exposes an interrupted state if persistence fails.
            with suppress(OSError):
                atomic(state_path, operation)
        if not announced:
            loop.call_soon_threadsafe(ready.set_exception, ValueError("today_operation_unavailable"))
