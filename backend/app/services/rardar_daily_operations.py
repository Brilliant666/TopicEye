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


async def _execution_paused() -> bool:
    """Respect the existing administrator switch at work-piece boundaries."""
    if not settings.RARDAR_DAILY_OPERATIONS_ENABLED:
        return False
    from sqlalchemy import select

    from app.models.scheduled_job import ScheduledJob

    async with async_session() as db:
        enabled = await db.scalar(select(ScheduledJob.enabled).where(ScheduledJob.job_key == "rardar_daily_operations"))
    return enabled is False


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
    from app.services.llm.daily_provider_budget import calendar_day
    from app.services.llm.provider_budget import news_execution_budget
    from app.services.rardar_hotspot_news import load_hotspot_news
    from app.services.rardar_news_quickread import enhance_hotspot_news

    if not _same_budget_day(ledger):
        return {"status": "partial", "reason": "calendar_day_changed", "waitReason": "calendar_day_changed"}

    # Freeze the complete managed public-news query, not just its home page.
    async with async_session() as db:
        first, _ = await load_hotspot_news(db, sort="latest", page_size=40)
        items = list(first.items)
        for page in range(2, first.totalPages + 1):
            result, _ = await load_hotspot_news(db, sort="latest", page=page, page_size=40)
            items.extend(result.items)
        # Freeze a run's IDs, not a moving home page. Two current items then one
        # historical item gives old debt a turn without draining it first.
        if "_queue" not in progress:
            cutoff = datetime.now(UTC) - timedelta(days=2)
            current, history = [], []
            for item in items:
                stamp = getattr(item, "updatedAt", None) or getattr(item, "publishedAt", None)
                identity = _digest(
                    item.model_dump(mode="json", exclude={"quickRead", "discoveryChannels", "fetchedAt"})
                )
                prior = progress.get(str(item.id), {})
                changed = prior.get("identity") is not None and prior["identity"] != identity
                (current if changed or (stamp is not None and stamp >= cutoff) else history).append(item.id)
            history.reverse()
            history_ids = list(history)
            queue = []
            while current or history:
                queue.extend(current[:2])
                del current[:2]
                queue.extend(history[:1])
                del history[:1]
            progress.update(
                _queue=queue,
                _seen=[],
                _outcomes={},
                _history=history_ids,
            )
            save()
        by_id = {item.id: item for item in items}
        seen = set(progress["_seen"])
        piece = [by_id[item_id] for item_id in progress["_queue"] if item_id not in seen and item_id in by_id][:6]
        result = {
            "status": "completed",
            "checked": len(progress["_queue"]),
            "processed": 0,
            "updated": 0,
            "cached": 0,
            "failed": 0,
        }
        day = calendar_day()
        if progress.get("_failureDay") != day:
            progress.update(_failureDay=day, _consecutiveFailures=0)
        consecutive_failures = progress.get("_consecutiveFailures", 0)
        with news_execution_budget(ledger):
            for item in piece:
                key = str(item.id)
                identity = _digest(
                    item.model_dump(mode="json", exclude={"quickRead", "discoveryChannels", "fetchedAt"})
                )
                # The business cache includes material, prompt and route identity.
                # A public-card/day-progress hash is not an equivalent cache key.
                if not _same_budget_day(ledger):
                    result.update(status="partial", reason="calendar_day_changed")
                    break
                previous = progress.get(key, {})
                attempts = (
                    previous.get("failedAttempts", 0)
                    if previous.get("identity") == identity and previous.get("day") == day
                    else 0
                )
                enhanced = await enhance_hotspot_news(
                    db,
                    frozen_page=SimpleNamespace(items=[item]),
                    allow_model=consecutive_failures < 2 and attempts < 2,
                )
                seen.add(item.id)
                progress["_seen"] = sorted(seen)
                progress["_outcomes"][key] = {
                    "processed": enhanced.considered,
                    "updated": enhanced.enhanced,
                    "cached": enhanced.cacheHits + enhanced.alreadyChinese,
                    "failed": enhanced.failed,
                }
                progress[key] = {
                    "identity": identity,
                    "complete": enhanced.status == "completed",
                    "day": day,
                    "failedAttempts": attempts + int(bool(enhanced.failed)),
                }
                if enhanced.status in {"waiting", "budget_exhausted"}:
                    details = getattr(enhanced, "items", [])
                    result["waitReason"] = next(
                        (entry.errorCode for entry in details if entry.errorCode), "daily_budget_exhausted"
                    )
                save()
                if enhanced.failed:
                    # Existing quickread handles bounded retries; no immediate repeat.
                    result["status"] = "partial"
                    consecutive_failures += 1
                elif enhanced.enhanced:
                    consecutive_failures = 0
                progress["_consecutiveFailures"] = consecutive_failures
                save()
            for value in progress["_outcomes"].values():
                for key in ("processed", "updated", "cached", "failed"):
                    result[key] += value[key]
            result["unfinished"] = max(0, result["checked"] - result["updated"] - result["cached"])
            result["hasMore"] = any(item_id not in seen for item_id in progress["_queue"] if item_id in by_id)
            result["historyPending"] = sum(
                str(item_id) not in progress["_outcomes"]
                or not (progress["_outcomes"][str(item_id)]["updated"] or progress["_outcomes"][str(item_id)]["cached"])
                for item_id in progress["_history"]
            )
            result["currentPending"] = max(0, result["unfinished"] - result["historyPending"])
            if result["unfinished"]:
                result.update(status="partial")
                result.setdefault("waitReason", "next_work_slice" if result["hasMore"] else "unfinished_items")
            return result


def _discover_child_matches(artifact, source, route: str) -> bool:
    from app.integrations.rardar.selection import _contract_versions

    return (
        artifact.assessedCount == 1
        and artifact.sourceObservationSetId == source.source_observation_set_id
        and artifact.sourceManifestSha256 == source.manifest_sha256
        and artifact.todayGenerationId == source.today_generation_id
        and artifact.modelRouteIdentity == route
        and artifact.contractVersions == _contract_versions()
    )


def _rotate_discover_work(batches: list, last_attempted) -> list:
    if not isinstance(last_attempted, int) or isinstance(last_attempted, bool) or not batches:
        return batches
    found = next((index for index, (_batch, ids) in enumerate(batches) if last_attempted in ids), None)
    offset = (
        (found + 1) % len(batches)
        if found is not None
        else next((index for index, (_batch, ids) in enumerate(batches) if ids[0] > last_attempted), 0)
    )
    return batches[offset:] + batches[:offset]


def _cached_profile_candidates(target: Path, universe: list, route: str) -> set[int]:
    """Read-only priority hint; the actual collector still revalidates evidence."""
    from pydantic import ValidationError

    from app.integrations.rardar.profile_cache_v2 import ProfileStoreEnvelopeV2, _read_plain, load_profile_store
    from app.integrations.rardar.selection import _profile_project
    from app.integrations.rardar.serving_profiles import _profile_identity_candidates, _profile_is_publishable
    from app.services.llm.provider_budget import ProviderBudgetError

    ready = set()
    for candidate in universe:
        for root in (target / "selection-profile-cache", target / "profile-cache"):
            directory = root / "profile-store/v2" / str(candidate.githubRepositoryId)
            try:
                plain(directory, missing=True)
                for path in sorted(directory.glob("*.json")):
                    raw = _read_plain(path, root=target)
                    if raw is None:
                        continue
                    record = ProfileStoreEnvelopeV2.model_validate_json(raw, strict=True)
                    if (
                        path.stem != record.cacheIdentity.identityDigest
                        or record.cacheIdentity.repositoryId != candidate.githubRepositoryId
                    ):
                        continue
                    if record.profile.repository != candidate.repository or not _profile_is_publishable(record.profile):
                        continue
                    if (
                        record.evidence.evidenceIndex.get("description", "")
                        != (candidate.description or "").strip()[:1000]
                    ):
                        continue
                    identities = _profile_identity_candidates(
                        _profile_project(candidate, 1),
                        record.evidence,
                        record.cacheIdentity.derivationMode,
                        route,
                    )
                    if record.cacheIdentity not in identities:
                        continue
                    route_required = record.profile.translationState == "translated" or (
                        record.profile.officialNarrativeMode in {"official_translated", "rardar_derived"}
                        and not record.deterministicFallbackUsed
                    )
                    if route_required and record.cacheIdentity.modelRouteIdentity != route:
                        continue
                    if load_profile_store(root, record.cacheIdentity) is not None:
                        ready.add(candidate.githubRepositoryId)
                        break
            except (OSError, ValueError, ValidationError, ProviderBudgetError):
                continue
    return ready


def _discover_retry_binding(target: Path, source, route: str, identifier: int) -> str:
    from app.integrations.rardar.selection import _cache_inventory_digest, _canonical_bytes, _contract_versions

    roots = [
        target / name / "profile-store/v2" / str(identifier) for name in ("selection-profile-cache", "profile-cache")
    ]
    for root in roots:
        plain(root, missing=True)
    return hashlib.sha256(
        _canonical_bytes(
            {
                "source": source.source_observation_set_id,
                "manifest": source.manifest_sha256,
                "today": source.today_generation_id,
                "route": route,
                "contracts": _contract_versions(),
                "project": identifier,
                "profiles": [_cache_inventory_digest(root) for root in roots],
            }
        )
    ).hexdigest()


async def _discover(
    target: Path, source, universe: list, ledger, progress: dict, save, *, max_batches: int | None = None, guard=None
) -> dict:
    from app.integrations.rardar.selection import _canonical_bytes, recall_candidates, selection_input_digest
    from app.integrations.rardar.selection_serving import SelectionServingLoader
    from app.services.llm.daily_provider_budget import ProviderWorkYield, calendar_day
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
                batches.extend((plan["recallBatchId"], (identifier,)) for identifier in ids)
                pending_ids.update(ids)
                resumed_plan_id = public["id"]
    ordinary_batches = []
    for offset in range(0, len(universe), 60):
        batch = f"managed-v1-{scope}-{offset}"
        page = [
            item for item in recall_candidates(universe, batch_id=batch) if item.githubRepositoryId not in pending_ids
        ]
        ordinary_batches.extend((batch, (item.githubRepositoryId,)) for item in page)
    # Cursor changes only ordering, never compatibility or assessment authority.
    # Advance even on a failed attempt so a repeatedly failing prefix cannot
    # consume every future day's opportunities. The fixed batch is not refilled.
    last_attempted = cursor.get("lastAttemptedId")
    ordinary_batches = _rotate_discover_work(ordinary_batches, last_attempted)
    profile_ready = _cached_profile_candidates(target, universe, route)
    ordinary_batches.sort(key=lambda item: item[1][0] not in profile_ready)
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
    with selection_execution_budget(ledger), run_failure_guard(isolate_stages=True, existing=guard) as guard:
        if not hasattr(guard, "attempted_candidates"):
            guard.attempted_candidates = set()
            guard.validated_children = {}
            guard.waiting_candidates = {}
            guard.reused_candidates = set()
        attempted_batches = 0
        for batch, ids in batches:
            if set(ids).issubset(guard.attempted_candidates):
                continue
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
            retry_day = calendar_day()
            retry_binding = _discover_retry_binding(target, source, route, ids[0])
            failed_attempts = (
                previous.get("failedAttempts", 0)
                if (previous.get("retryDay") == retry_day and previous.get("retryBinding") == retry_binding)
                else 0
            )
            if previous.get("binding") == binding and previous.get("complete"):
                # Durable progress is only an index, never authority for content.
                saved = SelectionServingLoader(target).validate_generation(previous["generationId"])
                guard.validated_children[previous["generationId"]] = saved
                if saved.inputDigest == binding and _discover_child_matches(saved, source, route):
                    result["reused"] += len(ids)
                    guard.reused_candidates.update(ids)
                    guard.attempted_candidates.update(ids)
                    continue
            if max_batches is not None and attempted_batches >= max_batches:
                result["status"] = "partial"
                break
            attempted_batches += 1
            cursor.update(lastAttemptedId=ids[-1], attemptedAt=datetime.now(UTC).isoformat())
            if resumed_plan_id and pending_ids == set(ids):
                cursor["manualPlanSeen"] = resumed_plan_id
            plain(cursor_path.parent, missing=True)
            cursor_path.parent.mkdir(parents=True, exist_ok=True)
            atomic(cursor_path, cursor)
            calls_before = ledger.snapshot()["attempted"]
            try:
                built = await rebuild(
                    target,
                    recall_batch_id=batch,
                    process_candidate_ids=ids,
                    expected_source_id=source.source_observation_set_id,
                    expected_today_generation=source.today_generation_id,
                    expected_route_identity=route,
                    publish=False,
                    provider_calls_allowed=failed_attempts < 2,
                )
            except ProviderWorkYield as exc:
                guard.attempted_candidates.update(ids)
                guard.waiting_candidates[ids[0]] = exc.code
                if resumed_plan_id and pending_ids.issubset(guard.attempted_candidates):
                    cursor["manualPlanSeen"] = resumed_plan_id
                    atomic(cursor_path, cursor)
                progress.setdefault("_waiting", {})[key] = {
                    "reason": exc.code,
                    "sourceObservationSetId": source.source_observation_set_id,
                    "todayGenerationId": source.today_generation_id,
                    "routeIdentity": route,
                }
                save()
                continue
            guard.waiting_candidates.pop(ids[0], None)
            progress.get("_waiting", {}).pop(key, None)
            artifact = SelectionServingLoader(target).validate_generation(built["selectionGenerationId"])
            guard.validated_children[built["selectionGenerationId"]] = artifact
            guard.attempted_candidates.update(ids)
            if resumed_plan_id and pending_ids.issubset(guard.attempted_candidates):
                cursor["manualPlanSeen"] = resumed_plan_id
                atomic(cursor_path, cursor)
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
                "sourceObservationSetId": artifact.sourceObservationSetId,
                "todayGenerationId": artifact.todayGenerationId,
                "completedCount": completed,
                "retryDay": retry_day,
                "retryBinding": _discover_retry_binding(target, source, route, ids[0]),
                "failedAttempts": failed_attempts
                + int(
                    completed != len(ids)
                    and failed_attempts < 2
                    and bool(
                        ledger.snapshot()["attempted"] > calls_before
                        or built.get("modelCalls", 0)
                        or built.get("githubRequests", 0)
                    )
                ),
            }
            save()
        result["hasMore"] = bool(set(ordered_ids) - guard.attempted_candidates)
    outcomes = {}
    for value in progress.values():
        if (
            isinstance(value, dict)
            and value.get("sourceObservationSetId") == source.source_observation_set_id
            and value.get("todayGenerationId") == source.today_generation_id
            and value.get("generationId")
        ):
            saved = guard.validated_children.get(value["generationId"])
            if saved is None:
                saved = SelectionServingLoader(target).validate_generation(value["generationId"])
                guard.validated_children[value["generationId"]] = saved
            if _discover_child_matches(saved, source, route):
                for row in saved.assessments:
                    identifier = row.candidate.githubRepositoryId
                    if identifier not in ordered_ids:
                        continue
                    precedence = (
                        getattr(saved, "generatedAt", datetime.min.replace(tzinfo=UTC)),
                        saved.selectionGenerationId,
                    )
                    if identifier not in outcomes or precedence > outcomes[identifier][0]:
                        outcomes[identifier] = (
                            precedence,
                            row.gate is not None and not row.valueFailureCode and not row.copyFailureCode,
                        )
    completed_total = sum(complete for _order, complete in outcomes.values())
    result["processed"] = len(outcomes)
    result["failed"] = len(outcomes) - completed_total
    result["completed"] = completed_total
    result["unfinished"] = len(universe) - completed_total
    result["waitingCount"] = len(guard.waiting_candidates)
    result["attemptedCount"] = len(set(outcomes) | set(guard.waiting_candidates))
    result["reused"] = len(guard.reused_candidates)
    if guard.waiting_candidates:
        result["waitReason"] = next(iter(guard.waiting_candidates.values()))
    attempts = [
        item
        for item in guard.validated_children.values()
        if getattr(item, "generatedAt", None) is not None and _discover_child_matches(item, source, route)
    ]
    if attempts:
        latest = max(attempts, key=lambda item: (item.generatedAt, item.selectionGenerationId))
        result["attemptGenerationId"] = latest.selectionGenerationId
        result["attemptedAt"] = latest.generatedAt.isoformat()
    if result["unfinished"] or result["waitingCount"]:
        result["status"] = "partial"
    result["newlyPublishedTotal"] = result.pop("published")
    try:
        current = SelectionServingLoader(target).validate_generation()
        result["currentPublishedCount"] = current.publishedCount
        result["currentGenerationId"] = current.selectionGenerationId
        pointer, _ = SelectionServingLoader(target)._pointer()
        result["currentPublishedAt"] = pointer.activatedAt.isoformat()
    except Exception:
        result["currentPublishedCount"] = None
    return result


def _publish_discover(target: Path, source, universe: list, progress: dict, *, route: str | None = None) -> dict:
    """Publish one period after its slices; no Provider work happens here."""
    from app.integrations.rardar.selection_period import publish_period, with_current_period
    from app.integrations.rardar.selection_serving import SelectionServingLoader

    if not any(isinstance(value, dict) and value.get("generationId") for value in progress.values()):
        return {"installed": False, "published": 0, "newlyPublishedTotal": 0, "reason": "no_completed_batch"}
    if route is None:
        raise ValueError("discover_route_unverified")
    allowed = {item.githubRepositoryId for item in universe}
    eligible = {}
    for value in progress.values():
        if not isinstance(value, dict) or not value.get("generationId"):
            continue
        # Saved progress is not authority, even when its metadata says current.
        child = SelectionServingLoader(target).validate_generation(value["generationId"])
        if not _discover_child_matches(child, source, route):
            continue
        identifier = child.assessments[0].candidate.githubRepositoryId
        if identifier not in allowed:
            continue
        previous = eligible.get(identifier)
        if previous is None or (child.generatedAt, child.selectionGenerationId) > (
            previous.generatedAt,
            previous.selectionGenerationId,
        ):
            eligible[identifier] = child
    generations = sorted(item.selectionGenerationId for item in eligible.values())
    if not generations:
        return {"installed": False, "published": 0, "newlyPublishedTotal": 0, "reason": "no_completed_batch"}
    installed = publish_period(
        target,
        with_current_period(target, generations),
        expected_source_id=source.source_observation_set_id,
        expected_today_generation=source.today_generation_id,
        expected_route_identity=route,
    )
    artifact = SelectionServingLoader(target).validate_generation(installed.selection_generation_id)
    pointer, _ = SelectionServingLoader(target)._pointer() if installed.current_changed else (None, None)
    return {
        "installed": installed.current_changed,
        "published": artifact.publishedCount,
        "newlyPublishedTotal": artifact.publishedCount if installed.current_changed else 0,
        "generationId": installed.selection_generation_id,
        "processed": artifact.processedCount,
        "unfinished": len(universe) - artifact.processedCount,
        "publishedAt": pointer.activatedAt.isoformat() if pointer else None,
        "reason": "published"
        if installed.current_changed
        else "unchanged"
        if artifact.currentEligible
        else "no_publishable_results"
        if artifact.semanticResolvedCount == artifact.processedCount
        else "partial_no_publishable_results",
    }


async def _public_materials(progress: dict, save, *, max_items: int | None = None) -> dict:
    """Refresh registered public Find/insight material, not historical questions."""
    from app.services.rardar_managed_materials import inventory_managed_materials
    from app.services.rardar_project_evidence import _persistent_root, collect_project_evidence

    root = _persistent_root()
    inventory = inventory_managed_materials(root.parent) if root else {"projects": [], "failed": 0}
    if max_items is None:
        progress.pop("_seen", None)
        progress.pop("_outcomes", None)
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
    seen = set(progress.setdefault("_seen", []))
    outcomes = progress.setdefault("_outcomes", {})
    work = 0
    for saved in inventory["projects"]:
        repository = saved.get("repository", "")
        if repository in seen:
            continue
        if max_items is not None and work >= max_items:
            break
        work += 1
        seen.add(repository)
        progress["_seen"] = sorted(seen)
        import re

        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9_][A-Za-z0-9_.-]*", repository):
            outcomes[repository] = "failed"
            continue
        binding = _digest(saved)
        if progress.get(repository) == binding:
            outcomes[repository] = "reused"
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
                outcomes[repository] = "failed"
                continue
            progress[repository] = binding
            outcomes[repository] = "updated"
            save()
        except Exception:
            outcomes[repository] = "failed"
    for outcome in outcomes.values():
        result[outcome] += 1
    result["processed"] = len(outcomes)
    result["hasMore"] = any(item.get("repository", "") not in seen for item in inventory["projects"])
    result["unfinished"] = max(0, result["checked"] - result["updated"] - result["reused"])
    save()
    if (
        any(
            result[key] for key in ("failed", "invalidCacheRecords", "invalidCurrentArtifact", "unresolvedProjectCount")
        )
        or result["hasMore"]
    ):
        result["status"] = "partial"
    return result


async def _today_profiles(target: Path, ledger, progress: dict | None = None) -> dict:
    from app.integrations.rardar.adapter import RardarIntelligenceAdapter
    from app.services.llm.daily_provider_budget import ProviderWorkYield, calendar_day
    from app.services.llm.provider_budget import selection_execution_budget
    from scripts.rebuild_rardar_serving import rebuild_async

    if not _same_budget_day(ledger):
        return {"status": "pending", "reason": "calendar_day_changed"}
    progress = progress if progress is not None else {}
    board = RardarIntelligenceAdapter.from_config(str(target)).load_explosion_board()
    ids = [project.githubRepositoryId for project in board.exactRanked[:20]]
    if progress.get("generation") != board.generationId:
        progress.clear()
        progress["generation"] = board.generationId
    seen = progress.setdefault("seen", [])
    pending = [identifier for identifier in ids if identifier not in seen]
    selected = pending[:1]
    if progress.get("failureDay") != calendar_day():
        progress.update(failureDay=calendar_day(), failedAttempts={})
    failed_attempts = progress["failedAttempts"]
    allowed = {identifier for identifier in selected if failed_attempts.get(str(identifier), 0) < 2}
    # Only this project's expensive work is enabled; all other verified
    # profiles/facts still take the normal cache-only projection path.
    seen.extend(selected)
    wait_reason = None
    try:
        with selection_execution_budget(ledger):
            value = await rebuild_async(
                target, concurrency=1, generate_profiles=bool(allowed), model_project_ids=allowed
            )
    except ProviderWorkYield as exc:
        # A missing model result is waiting, not a failed Profile. Keep scanning
        # later projects' real caches without allowing a new paid dispatch.
        if len(pending) > len(selected):
            return {
                **progress.get("lastResult", {}),
                "status": "pending",
                "checked": len(ids),
                "waitReason": exc.code,
                "hasMore": True,
            }
        # Finish the pass with normal fact-first cache projection even when
        # every expensive attempt waited. This never enables a Provider call.
        value = await rebuild_async(target, concurrency=1, generate_profiles=False, model_project_ids=set())
        wait_reason = exc.code
    if wait_reason is None:
        for identifier in allowed:
            key = str(identifier)
            if value.get("profileFailureCodes", {}).get(key):
                failed_attempts[key] = failed_attempts.get(key, 0) + 1
            else:
                failed_attempts.pop(key, None)
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
        hasMore=len(pending) > len(selected),
    )
    if wait_reason and result["unfinished"]:
        result["waitReason"] = wait_reason
    progress["lastResult"] = dict(result)
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
            if state.get("failureRetries", 0) >= MAX_DAILY_ATTEMPTS:
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
            material_progress = progress.setdefault("public_materials", {})
            material_progress.pop("_seen", None)
            material_progress.pop("_outcomes", None)
            try:
                modules["find_public_materials"] = await _public_materials(material_progress, save, max_items=6)
            except Exception as exc:
                modules["find_public_materials"] = {"status": "failed", "errorCode": _safe_error(exc)}
            save()
            from app.services.llm.daily_provider_budget import ProviderWorkYield, daily_execution_budget, work_slice

            try:
                budget = await daily_execution_budget("rardar_project_profile")
                ledger = budget[0] if budget else None
            except ProviderBudgetError:
                ledger = None
            if ledger is None:
                modules["discover"] = {"status": "pending", "reason": "daily_budget_not_configured"}
                modules["news_enhance"] = {"status": "pending", "reason": "daily_budget_not_configured"}
                modules["today_profiles"] = {"status": "pending", "reason": "daily_budget_not_configured"}
                # Public source checks do not require model configuration or
                # money. Continue bounded pieces without suppressing facts.
                for _ in range(100):
                    if not modules["find_public_materials"].get("hasMore") or await _execution_paused():
                        break
                    modules["find_public_materials"] = await _public_materials(material_progress, save, max_items=6)
                    save()
                    await asyncio.sleep(0)
            else:
                from app.services.llm.run_failure_guard import RunFailureGuard

                discover_guard = RunFailureGuard(isolate_stages=True)
                # A pass rechecks business caches; these transient cursors only
                # bound this invocation and never authorize a cached result.
                news_progress = progress.setdefault("news", {})
                for key in ("_queue", "_seen", "_outcomes", "_history"):
                    news_progress.pop(key, None)
                today_progress = progress.setdefault("today_profiles", {})
                today_progress.pop("seen", None)
                scheduling = state.setdefault("scheduling", {})
                scheduling.update(
                    sliceRequestLimit=6,
                    interactiveReserve=getattr(ledger, "interactive_reserve", 10),
                    preMorningBackgroundLimit=getattr(ledger, "early_background_limit", 20),
                    waitReason=None,
                )
                model_actions = (
                    (
                        "discover",
                        lambda: _discover(
                            target,
                            source,
                            universe,
                            ledger,
                            progress.setdefault("discover", {}),
                            save,
                            max_batches=1,
                            guard=discover_guard,
                        ),
                    ),
                    ("news_enhance", lambda: _news_enhance(ledger, progress.setdefault("news", {}), save)),
                    ("today_profiles", lambda: _today_profiles(target, ledger, today_progress)),
                    ("find_public_materials", lambda: _public_materials(material_progress, save, max_items=6)),
                )
                active = {name for name, _ in model_actions}
                if not modules["find_public_materials"].get("hasMore"):
                    active.discard("find_public_materials")
                # Bounded rounds rather than whole-inventory module monopolies.
                # Six is a dispatch slice, never a product coverage/quota gate.
                # Cache-only slices may keep advancing after money is exhausted.
                for _round in range(100):
                    if not active:
                        break
                    for name, action in model_actions:
                        if name not in active:
                            continue
                        if await _execution_paused():
                            scheduling["waitReason"] = "administrator_paused"
                            for pending_name in active:
                                modules[pending_name] = {
                                    **modules.get(pending_name, {}),
                                    "status": "pending",
                                    "waitReason": "administrator_paused",
                                }
                            active.clear()
                            break
                        if name != "find_public_materials" and not _same_budget_day(ledger):
                            modules[name] = {"status": "pending", "waitReason": "calendar_day_changed"}
                            active.discard(name)
                            save()
                            continue
                        if name == "discover" and source is None:
                            modules[name] = {"status": "pending", "waitReason": "source_unavailable"}
                            active.discard(name)
                            continue
                        prior_slices = modules.get(name, {}).get("workSlices", 0)
                        with work_slice(max_requests=6, background=True) as piece:
                            try:
                                modules[name] = await action()
                                if not modules[name].get("hasMore", False):
                                    active.discard(name)
                            except ProviderWorkYield as exc:
                                modules[name] = {**modules.get(name, {}), "status": "pending", "waitReason": exc.code}
                                # Saved stages survive; a later dispatch slot can
                                # continue a sliced project. Global waits yield
                                # to a later scheduled pass, not busy retries.
                                if exc.code != "work_slice_exhausted":
                                    active.discard(name)
                            except Exception as exc:
                                modules[name] = {"status": "failed", "errorCode": _safe_error(exc)}
                                active.discard(name)
                            modules[name]["workSlices"] = prior_slices + 1
                            modules[name]["lastSliceRequests"] = piece.used_requests
                        scheduling["workSlices"] = scheduling.get("workSlices", 0) + 1
                        save()
                        await asyncio.sleep(0)  # User requests can acquire the next dispatch slot.
                if active:
                    scheduling["waitReason"] = "next_scheduled_pass"
                if source is not None:
                    try:
                        from app.services.rardar_llm_control import resolve_rardar_route_identity

                        route = (
                            await resolve_rardar_route_identity()
                            if any(
                                isinstance(value, dict) and value.get("generationId")
                                for value in progress.setdefault("discover", {}).values()
                            )
                            else None
                        )
                        publication = await asyncio.to_thread(
                            _publish_discover,
                            target,
                            source,
                            universe,
                            progress.setdefault("discover", {}),
                            route=route,
                        )
                        modules["discover"]["publication"] = publication
                        if publication.get("installed"):
                            modules["discover"].update(
                                currentGenerationId=publication["generationId"],
                                currentPublishedCount=publication["published"],
                                newlyPublishedTotal=publication["published"],
                                currentPublishedAt=publication.get("publishedAt"),
                            )
                    except Exception as exc:
                        modules["discover"].update(status="partial", publicationError=_safe_error(exc))
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
            # Cooperative waits are not failed executions. In particular a
            # pause/resume or depleted budget cannot exhaust the failure retry
            # allowance before a later legitimate dispatch opportunity.
            cooperative_wait = any(
                value.get("waitReason")
                or value.get("reason") in {"daily_budget_not_configured", "calendar_day_changed"}
                for value in modules.values()
            )
            if not cooperative_wait and any(value.get("status") == "failed" for value in modules.values()):
                state["failureRetries"] = state.get("failureRetries", 0) + 1
            save()
            return {key: value for key, value in state.items() if key != "progress"}
    except ProviderBudgetError as exc:
        if exc.code != "provider_budget_busy":
            raise
        return {"status": "skipped", "reason": "already_running"}
