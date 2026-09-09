"""Daily orchestration of existing Rardar business entries, not a second scheduler.

The scheduler's existing DB lease and this OS lock protect one local data root.
Durable per-day progress bounds retries and makes restarts/catch-up idempotent.
Facts continue independently of optional model work and its shared daily cap.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.core.database import async_session
from app.services.llm.provider_budget import ProviderBudgetError, atomic, file_lock, plain

ZONE = ZoneInfo("Asia/Shanghai")
MAX_DAILY_ATTEMPTS = 3


def operation_root() -> Path:
    identity = hashlib.sha256(settings.RARDAR_INTELLIGENCE_DATA_DIR.encode()).hexdigest()[:20]
    home = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "state")
    root = home / "TopicEye" / "daily-operations" / identity
    plain(root, missing=True)
    return root


def _read(path: Path) -> dict:
    plain(path, missing=True)
    if not path.exists():
        return {}
    if path.stat().st_size > 4_000_000:
        raise ValueError("daily_state_invalid")
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError("daily_state_invalid")
    return value


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def latest_status() -> dict:
    root = operation_root()
    state = _read(root / "latest.json")
    if state.get("status") != "running":
        return state
    lock = root / "writer.lock"
    plain(lock, missing=True)
    if lock.exists():
        try:
            with file_lock(lock, blocking=False):
                pass
        except ProviderBudgetError as exc:
            if exc.code == "provider_budget_busy":
                return state
            raise
    # A process killed outside Python cannot run finally. Project an orphan as
    # interrupted without mutating history or claiming that work completed.
    return {**state, "status": "interrupted", "errorCode": "executor_interrupted"}


@contextmanager
def _record_interruption(path: Path):
    """Runs while the writer lock is still held, so cancellation cannot race a resume."""
    try:
        yield
    except BaseException as exc:
        state = _read(path)
        if state.get("status") == "running":
            interrupted = isinstance(exc, asyncio.CancelledError | KeyboardInterrupt | SystemExit)
            state.update(
                status="interrupted" if interrupted else "failed",
                errorCode="executor_interrupted" if interrupted else _safe_error(exc),
                completedAt=datetime.now(UTC).isoformat(),
            )
            atomic(path, state)
            atomic(path.parent / "latest.json", {key: value for key, value in state.items() if key != "progress"})
        raise


def _safe_error(exc: Exception) -> str:
    import re

    code = getattr(exc, "code", None)
    return code if isinstance(code, str) and re.fullmatch(r"[a-z][a-z0-9_]{1,100}", code) else type(exc).__name__


def _same_budget_day(ledger) -> bool:
    from app.services.llm.daily_provider_budget import calendar_day
    from app.services.llm.provider_budget import DAILY_TASK_ID

    return ledger.task_id != DAILY_TASK_ID or ledger.run_id == f"daily-{calendar_day()}"


async def _today() -> dict:
    from uuid import uuid4

    from app.schemas.rardar_today_operations import TodayOperationRequest
    from app.services.rardar_today_operations import get_operation, start_operation

    operation = await start_operation(TodayOperationRequest(requestId=uuid4()), user_id=0)
    # The existing worker owns its writer lock even if this waiter is cancelled.
    async with asyncio.timeout(600):
        while operation["status"] == "running":
            await asyncio.sleep(1)
            operation = get_operation(operation["id"])
    return {key: operation.get(key) for key in ("id", "status", "result", "errorCode")}


async def _news_refresh() -> dict:
    from app.services.rardar_hotspot_news import refresh_hotspot_news

    async with async_session() as db:
        result = await refresh_hotspot_news(db)
    return result.model_dump(mode="json")


async def _inventory(target: Path) -> tuple[dict, object, list]:
    from app.integrations.rardar.selection import build_candidate_universe
    from app.integrations.rardar.selection_execution import selection_writer
    from app.integrations.rardar.selection_source import SelectionSourceAdapter, install_selection_source
    from app.integrations.rardar.selection_source_local import build_selection_source_from_today_mirror
    from app.integrations.rardar.serving import ServingProjectionLoader

    with selection_writer(target):
        today, _etag = await asyncio.to_thread(ServingProjectionLoader(str(target)).load_today_with_etag)
        built = await asyncio.to_thread(
            build_selection_source_from_today_mirror, target, expected_today_generation=today.generationId
        )
        await asyncio.to_thread(install_selection_source, target, built)
        source = await asyncio.to_thread(SelectionSourceAdapter.from_config(str(target)).load)
        universe, summary = build_candidate_universe(source)
    return (
        {
            "status": "checked",
            "sourceObservationSetId": source.source_observation_set_id,
            "todayGenerationId": today.generationId,
            "latestCaptureAt": source.latest_capture_at,
            "managedCandidateCount": len(universe),
            "todayProjectCount": len(source.today["exactRanked"][:20]),
            "universe": asdict(summary),
            "checked": len(source.captures[-1]["observations"]),
            "checkKind": "validated_public_repository_facts_not_completed_ai_profiles",
        },
        source,
        universe,
    )


async def _news_enhance(ledger, progress: dict, save) -> dict:
    from app.services.llm.provider_budget import news_execution_budget
    from app.services.rardar_hotspot_news import load_hotspot_news
    from app.services.rardar_news_quickread import enhance_hotspot_news

    # Freeze the complete managed public-news query, not just its home page.
    async with async_session() as db:
        first, _ = await load_hotspot_news(db, sort="latest", page_size=40)
        items = list(first.items)
        for page in range(2, first.totalPages + 1):
            result, _ = await load_hotspot_news(db, sort="latest", page=page, page_size=40)
            items.extend(result.items)
        result = {"status": "completed", "checked": len(items), "processed": 0, "updated": 0, "cached": 0, "failed": 0}
        consecutive_failures = 0
        with news_execution_budget(ledger):
            for item in items:
                key = str(item.id)
                identity = _digest(item.model_dump(mode="json", exclude={"quickRead"}))
                # The business cache includes material, prompt and route identity.
                # A public-card/day-progress hash is not an equivalent cache key.
                if not _same_budget_day(ledger):
                    result.update(status="partial", reason="calendar_day_changed")
                    break
                if ledger.snapshot()["remaining"] == 0:
                    result["status"] = "partial"
                    break
                enhanced = await enhance_hotspot_news(db, frozen_page=SimpleNamespace(items=[item]))
                result["processed"] += enhanced.considered
                result["updated"] += enhanced.enhanced
                result["cached"] += enhanced.cacheHits + enhanced.alreadyChinese
                result["failed"] += enhanced.failed
                progress[key] = {"identity": identity, "complete": enhanced.status == "completed"}
                save()
                if enhanced.failed:
                    # Existing quickread handles bounded retries; no immediate repeat.
                    result["status"] = "partial"
                    consecutive_failures += 1
                    if consecutive_failures >= 2:
                        break
                else:
                    consecutive_failures = 0
            result["unfinished"] = max(0, len(items) - result["updated"] - result["cached"])
            return result


async def _discover(target: Path, source, universe: list, ledger, progress: dict, save) -> dict:
    from app.integrations.rardar.selection import _canonical_bytes, recall_candidates, selection_input_digest
    from app.integrations.rardar.selection_serving import SelectionServingLoader
    from app.services.llm.provider_budget import selection_execution_budget
    from app.services.llm.run_failure_guard import run_failure_guard
    from app.services.rardar_llm_control import resolve_rardar_route_identity
    from scripts.rebuild_rardar_discover_selection import rebuild

    route = await resolve_rardar_route_identity()
    ordered_ids = sorted(item.githubRepositoryId for item in universe)
    scope = hashlib.sha256(_canonical_bytes(ordered_ids)).hexdigest()[:24]
    batches = []
    pending_ids = set()
    cursor_path = operation_root() / "discover-cursor.json"
    cursor = _read(cursor_path)
    resumed_plan_id = None
    # A saved interrupted/manual batch gets the first continuation opportunity.
    # Its Profile caches remain subject to the normal evidence/route binding.
    from app.services import rardar_discover_operations as manual

    previous_operation = manual.latest_operation()
    if previous_operation and previous_operation.get("status") in {"failed", "interrupted"}:
        public = previous_operation["plan"]
        plan = manual._read(manual.operation_root() / "plans" / f"{public['id']}.json")
        if (
            plan
            and plan["sourceObservationSetId"] == source.source_observation_set_id
            and plan["routeIdentity"] == route
            and plan.get("todayGenerationId") == source.today_generation_id
            and plan.get("binding") == manual._binding(source, route)
            and cursor.get("manualPlanSeen") != public["id"]
        ):
            ids = tuple(item["githubRepositoryId"] for item in plan["candidates"])
            if set(ids).issubset(ordered_ids):
                batches.append((plan["recallBatchId"], ids))
                pending_ids.update(ids)
                resumed_plan_id = public["id"]
    ordinary_batches = []
    for offset in range(0, len(universe), 60):
        batch = f"managed-v1-{scope}-{offset}"
        page = [
            item for item in recall_candidates(universe, batch_id=batch) if item.githubRepositoryId not in pending_ids
        ]
        ordinary_batches.extend(
            (batch, tuple(item.githubRepositoryId for item in page[start : start + 6]))
            for start in range(0, len(page), 6)
        )
    # Cursor changes only ordering, never compatibility or assessment authority.
    # Advance even on a failed attempt so a repeatedly failing prefix cannot
    # consume every future day's opportunities. The fixed batch is not refilled.
    last_attempted = cursor.get("lastAttemptedId")
    if isinstance(last_attempted, int) and not isinstance(last_attempted, bool) and ordinary_batches:
        offset = next((index for index, (_batch, ids) in enumerate(ordinary_batches) if ids[0] > last_attempted), 0)
        ordinary_batches = ordinary_batches[offset:] + ordinary_batches[:offset]
    batches.extend(ordinary_batches)
    result = {
        "status": "completed",
        "checked": len(universe),
        "processed": 0,
        "completed": 0,
        "published": 0,
        "failed": 0,
        "reused": 0,
    }
    with selection_execution_budget(ledger), run_failure_guard() as guard:
        for batch, ids in batches:
            if not _same_budget_day(ledger):
                result.update(status="partial", reason="calendar_day_changed")
                break
            key = ",".join(map(str, ids))
            binding = selection_input_digest(
                source,
                cache_root=target / "selection-profile-cache",
                model_route_identity=route,
                recall_limit=48,
                recall_batch_id=batch,
                process_candidate_ids=ids,
            )
            previous = progress.get(key, {})
            if previous.get("binding") == binding and previous.get("complete"):
                # Durable progress is only an index, never authority for content.
                saved = SelectionServingLoader(target).validate_generation(previous["generationId"])
                if saved.inputDigest == binding:
                    result["reused"] += len(ids)
                    continue
            if guard.stopped or ledger.snapshot()["remaining"] == 0:
                result["status"] = "partial"
                break
            cursor.update(lastAttemptedId=ids[-1], attemptedAt=datetime.now(UTC).isoformat())
            if resumed_plan_id and pending_ids == set(ids):
                cursor["manualPlanSeen"] = resumed_plan_id
            plain(cursor_path.parent, missing=True)
            cursor_path.parent.mkdir(parents=True, exist_ok=True)
            atomic(cursor_path, cursor)
            built = await rebuild(
                target,
                recall_batch_id=batch,
                process_candidate_ids=ids,
                expected_source_id=source.source_observation_set_id,
                expected_today_generation=source.today_generation_id,
                expected_route_identity=route,
            )
            artifact = SelectionServingLoader(target).validate_generation(built["selectionGenerationId"])
            completed = sum(
                item.gate is not None and not item.valueFailureCode and not item.copyFailureCode
                for item in artifact.assessments
            )
            result["processed"] += len(ids)
            result["completed"] += completed
            result["failed"] += len(ids) - completed
            if built.get("currentChanged"):
                result["published"] += artifact.publishedCount
            progress[key] = {
                "binding": artifact.inputDigest,
                "complete": completed == len(ids),
                "generationId": built["selectionGenerationId"],
            }
            save()
    result["unfinished"] = len(universe) - result["completed"] - result["reused"]
    if result["unfinished"]:
        result["status"] = "partial"
    result["newlyPublishedTotal"] = result.pop("published")
    try:
        current = SelectionServingLoader(target).validate_generation()
        result["currentPublishedCount"] = current.publishedCount
        result["currentGenerationId"] = current.selectionGenerationId
    except Exception:
        result["currentPublishedCount"] = None
    return result


async def _public_materials(progress: dict, save) -> dict:
    """Refresh registered public Find/insight material, not historical questions."""
    from app.services.rardar_managed_materials import inventory_managed_materials
    from app.services.rardar_project_evidence import _persistent_root, collect_project_evidence

    root = _persistent_root()
    inventory = inventory_managed_materials(root.parent) if root else {"projects": [], "failed": 0}
    result = {
        "status": "completed",
        "checked": len(inventory["projects"]),
        "updated": 0,
        "reused": 0,
        "failed": 0,
        **{
            key: inventory.get(key, 0)
            for key in (
                "invalidCacheRecords",
                "incompatibleCacheRecords",
                "invalidCurrentArtifact",
                "unresolvedProjectCount",
            )
        },
    }
    for saved in inventory["projects"]:
        repository = saved.get("repository", "")
        import re

        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9_][A-Za-z0-9_.-]*", repository):
            result["failed"] += 1
            continue
        binding = _digest(saved)
        if progress.get(repository) == binding:
            result["reused"] += 1
            continue
        try:
            options = saved.get("options", {})
            evidence = await collect_project_evidence(
                repository,
                saved.get("facts", {}),
                include_readme_body=options.get("include_readme_body") is True,
                readme_only=options.get("readme_only") is True,
                refresh_material=True,
            )
            if not evidence.payload["readme"]["path"]:
                result["failed"] += 1
                continue
            progress[repository] = binding
            result["updated"] += 1
            save()
        except Exception:
            result["failed"] += 1
    if any(
        result[key] for key in ("failed", "invalidCacheRecords", "invalidCurrentArtifact", "unresolvedProjectCount")
    ):
        result["status"] = "partial"
    return result


async def _today_profiles(target: Path, ledger) -> dict:
    from app.services.llm.provider_budget import selection_execution_budget
    from scripts.rebuild_rardar_serving import rebuild_async

    if not _same_budget_day(ledger):
        return {"status": "pending", "reason": "calendar_day_changed"}
    if ledger.snapshot()["remaining"] == 0:
        return {"status": "pending", "reason": "daily_budget_exhausted"}
    with selection_execution_budget(ledger):
        value = await rebuild_async(target, concurrency=1, generate_profiles=True)
    result = {
        key: value[key]
        for key in ("status", "changed", "servingGenerationId", "profiles", "translationCalls", "translationCacheHits")
    }
    summary = value["profiles"]
    result.update(
        checked=summary["total"],
        completed=summary["complete"],
        unfinished=summary["partial"] + summary["sourceUnavailable"],
        status="partial" if summary["partial"] or summary["sourceUnavailable"] else "completed",
    )
    return result


async def run_daily_operations() -> dict:
    now = datetime.now(UTC)
    local = now.astimezone(ZONE)
    # A midnight manual catch-up must not consume the coming 08:30 check.
    # Operation cycles follow the publication schedule; cost always follows
    # the Shanghai calendar day at the actual dispatch instant.
    cycle_date = local.date() - timedelta(days=1) if (local.hour, local.minute) < (8, 30) else local.date()
    if not settings.RARDAR_INTELLIGENCE_DATA_DIR:
        return {"status": "failed", "reason": "data_not_configured"}
    root = operation_root()
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{cycle_date.isoformat()}.json"
    try:
        with file_lock(root / "writer.lock", blocking=False), _record_interruption(path):
            state = _read(path)
            if state.get("status") == "completed":
                return {**state, "status": "skipped", "reason": "already_completed"}
            if state.get("attempts", 0) >= MAX_DAILY_ATTEMPTS:
                return {**state, "status": "skipped", "reason": "daily_retry_limit"}
            state.update(
                date=cycle_date.isoformat(),
                status="running",
                startedAt=now.isoformat(),
                attempts=state.get("attempts", 0) + 1,
            )
            modules = state.setdefault("modules", {})
            progress = state.setdefault("progress", {})

            def save():
                atomic(path, state)
                atomic(root / "latest.json", {key: value for key, value in state.items() if key != "progress"})

            save()
            for name, action in (("today", _today), ("news_refresh", _news_refresh)):
                if modules.get(name, {}).get("status") in {
                    "completed",
                    "updated",
                    "unchanged",
                    "no_complete_board",
                    "paused",
                }:
                    continue
                try:
                    modules[name] = await action()
                except Exception as exc:
                    modules[name] = {"status": "failed", "errorCode": _safe_error(exc)}
                save()
            target = Path(settings.RARDAR_INTELLIGENCE_DATA_DIR)
            source, universe = None, []
            try:
                modules["public_projects"], source, universe = await _inventory(target)
            except Exception as exc:
                modules["public_projects"] = {"status": "failed", "errorCode": _safe_error(exc)}
            save()
            try:
                modules["find_public_materials"] = await _public_materials(
                    progress.setdefault("public_materials", {}), save
                )
            except Exception as exc:
                modules["find_public_materials"] = {"status": "failed", "errorCode": _safe_error(exc)}
            save()
            from app.services.llm.daily_provider_budget import daily_execution_budget

            try:
                budget = await daily_execution_budget("rardar_project_profile")
                ledger = budget[0] if budget else None
            except ProviderBudgetError:
                ledger = None
            if ledger is None:
                modules["discover"] = {"status": "pending", "reason": "daily_budget_not_configured"}
                modules["news_enhance"] = {"status": "pending", "reason": "daily_budget_not_configured"}
                modules["today_profiles"] = {"status": "pending", "reason": "daily_budget_not_configured"}
            else:
                model_actions = (
                    (
                        "discover",
                        lambda: _discover(target, source, universe, ledger, progress.setdefault("discover", {}), save),
                    ),
                    ("news_enhance", lambda: _news_enhance(ledger, progress.setdefault("news", {}), save)),
                    ("today_profiles", lambda: _today_profiles(target, ledger)),
                )
                # Shared daily cap, no per-module budget. Rotate the first
                # opportunity across cycles and bounded retries to avoid a
                # permanently hungry prefix consuming all 100 every day.
                rotation = (cycle_date.toordinal() + state["attempts"] - 1) % len(model_actions)
                model_actions = model_actions[rotation:] + model_actions[:rotation]
                for name, action in model_actions:
                    if not _same_budget_day(ledger):
                        modules[name] = {"status": "pending", "reason": "calendar_day_changed"}
                        save()
                        continue
                    if name == "discover" and source is None:
                        modules[name] = {"status": "pending", "reason": "source_unavailable"}
                        continue
                    try:
                        modules[name] = await action()
                    except Exception as exc:
                        modules[name] = {"status": "failed", "errorCode": _safe_error(exc)}
                    save()
                state["budget"] = {key: ledger.snapshot()[key] for key in ("attempted", "limit", "remaining")}
            state.update(
                status="partial"
                if any(
                    value.get("status")
                    in {"partial", "pending", "failed", "degraded", "busy", "interrupted", "not_configured"}
                    for value in modules.values()
                )
                else "completed",
                completedAt=datetime.now(UTC).isoformat(),
            )
            save()
            return {key: value for key, value in state.items() if key != "progress"}
    except ProviderBudgetError as exc:
        if exc.code != "provider_budget_busy":
            raise
        return {"status": "skipped", "reason": "already_running"}
