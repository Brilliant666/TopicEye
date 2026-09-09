"""Bounded admin operations over the existing Selection CLI business flow."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from app.core.config import settings
from app.integrations.rardar.selection import (
    _contract_versions,
    build_candidate_universe,
    recall_candidates,
)
from app.integrations.rardar.selection_execution import selection_writer
from app.integrations.rardar.selection_serving import SelectionServingError, SelectionServingLoader
from app.integrations.rardar.selection_source import SelectionSourceAdapter, install_selection_source
from app.integrations.rardar.selection_source_local import build_selection_source_from_today_mirror
from app.integrations.rardar.serving import ServingProjectionLoader
from app.schemas.rardar_discover_operations import DiscoverOperationRequest, DiscoverPrepareRequest
from app.services.llm.provider_budget import ProviderBudgetError, ProviderBudgetLedger, atomic, file_lock, plain
from app.services.rardar_llm_control import resolve_rardar_route_identity

BATCH_SIZE = 6
TASK_ID = "RARDAR-DISCOVER-DAILY-OPERATION"
_tasks: set[asyncio.Task] = set()


def request_limit() -> int:
    limit = settings.RARDAR_DISCOVER_REQUEST_LIMIT
    if isinstance(limit, bool) or not 1 <= limit <= 100:
        raise ValueError("discover_request_limit_invalid")
    return limit


def operation_root() -> Path:
    identity = hashlib.sha256(settings.RARDAR_INTELLIGENCE_DATA_DIR.encode()).hexdigest()[:20]
    home = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / ".local" / "state"))
    root = home / "TopicEye" / "discover-operations" / identity
    plain(root, missing=True)
    return root


def _read(path: Path) -> dict[str, Any] | None:
    plain(path, missing=True)
    if not path.exists():
        return None
    if path.stat().st_size > 500_000:
        raise ValueError("discover_operation_state_invalid")
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError("discover_operation_state_invalid")
    return value


def _public_plan(plan: dict) -> dict:
    allowed = {
        "id",
        "candidates",
        "candidateCount",
        "sourceObservationSetId",
        "todayGenerationId",
        "latestCaptureAt",
        "requestLimit",
        "recallBatchId",
    }
    return {key: value for key, value in plan.items() if key in allowed}


def _ledger(identifier: str) -> ProviderBudgetLedger:
    saved = _read(operation_root() / identifier / "operation.json")
    return ProviderBudgetLedger(
        operation_root() / identifier / "provider-budget.json",
        identifier,
        task_id=TASK_ID,
        limit=saved["plan"]["requestLimit"],
    )


def get_operation(identifier: str) -> dict | None:
    identifier = str(UUID(identifier))
    saved = _read(operation_root() / identifier / "operation.json")
    if saved is None:
        return None
    if (operation_root() / identifier / "provider-budget.json").exists():
        saved["providerCalls"] = _ledger(identifier).snapshot()["attempted"]
    if saved["status"] == "running":
        latest = _read(operation_root() / "latest-operation.json")
        if not latest or latest.get("id") != identifier:
            return {**saved, "status": "interrupted", "errorCode": "discover_executor_interrupted"}
        try:
            with file_lock(operation_root() / "writer.lock", blocking=False):
                pass
        except ProviderBudgetError as exc:
            if exc.code != "provider_budget_busy":
                raise
        else:
            saved = {**saved, "status": "interrupted", "errorCode": "discover_executor_interrupted"}
    return saved


def latest_operation() -> dict | None:
    latest = _read(operation_root() / "latest-operation.json")
    return get_operation(latest["id"]) if latest else None


def prepared_plan() -> dict | None:
    latest = _read(operation_root() / "latest-plan.json")
    if latest and _read(operation_root() / f"executed-{latest['id']}.json"):
        return None
    plan = _read(operation_root() / "plans" / f"{latest['id']}.json") if latest else None
    return _public_plan(plan) if plan else None


def _binding(source, route: str) -> str:
    return hashlib.sha256(
        json.dumps(
            {
                "source": source.source_observation_set_id,
                "manifest": source.manifest_sha256,
                "route": route,
                "contracts": _contract_versions(),
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()


async def prepare_operation(payload: DiscoverPrepareRequest, *, user_id: int) -> dict:
    if not settings.RARDAR_INTELLIGENCE_DATA_DIR:
        raise ValueError("discover_not_configured")
    root = operation_root()
    root.mkdir(parents=True, exist_ok=True)
    with file_lock(root / "admission.lock", blocking=False):
        key = root / f"prepare-{user_id}-{payload.requestId}.json"
        previous = _read(key)
        if previous:
            return _public_plan(_read(root / "plans" / f"{previous['id']}.json"))
        current = latest_operation()
        if current and current["status"] == "running":
            return current["plan"]
        with (
            file_lock(root / "writer.lock", blocking=False),
            selection_writer(Path(settings.RARDAR_INTELLIGENCE_DATA_DIR)),
        ):
            target = Path(settings.RARDAR_INTELLIGENCE_DATA_DIR)
            today, _etag = ServingProjectionLoader(str(target)).load_today_with_etag()
            built = await asyncio.to_thread(
                build_selection_source_from_today_mirror, target, expected_today_generation=today.generationId
            )
            install_selection_source(target, built)
            source = SelectionSourceAdapter.from_config(str(target)).load()
            route = await resolve_rardar_route_identity()
            binding = _binding(source, route)
            latest_plan = _read(root / "latest-plan.json")
            if latest_plan and not _read(root / f"executed-{latest_plan['id']}.json"):
                prepared = _read(root / "plans" / f"{latest_plan['id']}.json")
                if prepared and prepared["binding"] == binding:
                    atomic(key, {"id": prepared["id"]})
                    return _public_plan(prepared)
            completed: set[int] = set()
            attempted: set[int] = set()
            try:
                active = SelectionServingLoader(target).validate_generation()
            except SelectionServingError:
                active = None
            if (
                active is not None
                and active.sourceObservationSetId == source.source_observation_set_id
                and active.modelRouteIdentity == route
                and active.contractVersions == _contract_versions()
            ):
                completed.update(
                    item.candidate.githubRepositoryId
                    for item in active.assessments
                    if item.gate is not None and not item.valueFailureCode and not item.copyFailureCode
                )
            sequence = 0
            for state_path in root.glob("*/operation.json"):
                saved = _read(state_path)
                if not saved:
                    continue
                saved_plan = _read(root / "plans" / f"{saved['plan']['id']}.json")
                if not saved_plan or saved_plan["binding"] != binding:
                    continue
                sequence += 1
                attempted.update(item["githubRepositoryId"] for item in saved_plan["candidates"])
                if saved.get("result"):
                    completed.update(saved["result"].get("completedCandidateIds", []))
            identifier = str(uuid4())
            batch_id = f"daily-{source.source_observation_set_id}-{sequence + 1}"
            universe, _summary = build_candidate_universe(source)
            recalled = recall_candidates(universe, 48, batch_id=batch_id)
            # Prioritize unseen/incomplete facts, while preserving the exact
            # recall order required by the existing small-batch builder.
            priority = sorted(
                recalled, key=lambda item: (item.githubRepositoryId in completed, item.githubRepositoryId in attempted)
            )[:BATCH_SIZE]
            selected = {item.githubRepositoryId for item in priority}
            candidates = [
                {"githubRepositoryId": item.githubRepositoryId, "repository": item.repository}
                for item in recalled
                if item.githubRepositoryId in selected
            ]
            plan = {
                "id": identifier,
                "candidates": candidates,
                "candidateCount": len(candidates),
                "sourceObservationSetId": source.source_observation_set_id,
                "todayGenerationId": source.today_generation_id,
                "latestCaptureAt": source.latest_capture_at,
                "requestLimit": request_limit(),
                "recallBatchId": batch_id,
                "routeIdentity": route,
                "binding": binding,
            }
            (root / "plans").mkdir(exist_ok=True)
            atomic(root / "plans" / f"{identifier}.json", plan)
            atomic(key, {"id": identifier})
            atomic(root / "latest-plan.json", {"id": identifier})
            return _public_plan(plan)


async def start_operation(payload: DiscoverOperationRequest, *, user_id: int) -> dict:
    if not settings.RARDAR_INTELLIGENCE_DATA_DIR:
        raise ValueError("discover_not_configured")
    root = operation_root()
    root.mkdir(parents=True, exist_ok=True)
    with file_lock(root / "admission.lock", blocking=False):
        key = root / f"request-{user_id}-{payload.requestId}.json"
        previous = _read(key) or _read(root / f"executed-{payload.planId}.json")
        if previous:
            return get_operation(previous["id"])
        latest = latest_operation()
        if latest and latest["status"] == "running":
            atomic(key, {"id": latest["id"]})
            return latest
        plan = _read(root / "plans" / f"{payload.planId}.json")
        if not plan:
            raise ValueError("discover_plan_missing")
        prepared = _read(root / "latest-plan.json")
        if not prepared or prepared["id"] != plan["id"]:
            raise ValueError("discover_plan_superseded")
        future = asyncio.get_running_loop().create_future()
        task = asyncio.create_task(_execute(plan, key, future))
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)
        return await asyncio.shield(future)


async def _run(plan: dict, ledger: ProviderBudgetLedger, report) -> dict:
    from app.services.llm.provider_budget import selection_execution_budget
    from app.services.llm.run_failure_guard import run_failure_guard
    from scripts.rebuild_rardar_discover_selection import rebuild

    with selection_execution_budget(ledger), run_failure_guard() as guard:
        result = await rebuild(
            Path(settings.RARDAR_INTELLIGENCE_DATA_DIR),
            recall_batch_id=plan["recallBatchId"],
            process_candidate_ids=tuple(item["githubRepositoryId"] for item in plan["candidates"]),
            report_stage=report,
            expected_source_id=plan["sourceObservationSetId"],
            expected_today_generation=plan["todayGenerationId"],
            expected_route_identity=plan["routeIdentity"],
        )
        return {**result, "stopped": guard.stopped, "stopReason": guard.failure_code if guard.stopped else None}


async def _execute(plan: dict, key: Path, ready: asyncio.Future) -> None:
    operation = None
    try:
        with (
            file_lock(operation_root() / "writer.lock", blocking=False),
            selection_writer(Path(settings.RARDAR_INTELLIGENCE_DATA_DIR)),
        ):
            target = Path(settings.RARDAR_INTELLIGENCE_DATA_DIR)
            source = SelectionSourceAdapter.from_config(str(target)).load()
            today, _etag = ServingProjectionLoader(str(target)).load_today_with_etag()
            route = await resolve_rardar_route_identity()
            if today.generationId != plan["todayGenerationId"] or _binding(source, route) != plan["binding"]:
                raise ValueError("discover_plan_changed")
            identifier = str(uuid4())
            path = operation_root() / identifier / "operation.json"
            path.parent.mkdir()
            operation = {
                "id": identifier,
                "status": "running",
                "plan": _public_plan(plan),
                "providerCalls": 0,
                "startedAt": datetime.now(UTC).isoformat(),
                "completedAt": None,
                "result": None,
                "errorCode": None,
                "stage": "preparing",
            }
            atomic(path, operation)
            atomic(key, {"id": identifier})
            atomic(operation_root() / f"executed-{plan['id']}.json", {"id": identifier})
            atomic(operation_root() / "latest-operation.json", {"id": identifier})
            ledger = ProviderBudgetLedger.initialize(
                path.parent / "provider-budget.json", identifier, task_id=TASK_ID, limit=plan["requestLimit"]
            )
            ready.set_result(dict(operation))

            def report(stage: str) -> None:
                operation.update(stage=stage, providerCalls=ledger.snapshot()["attempted"])
                atomic(path, operation)

            if not plan["candidates"]:
                result = {"publishedCount": 0, "changed": False, "state": "empty", "cacheHits": 0}
                failures, completed = [], []
            else:
                result = await _run(plan, ledger, report)
                artifact = SelectionServingLoader(target).validate_generation(result["selectionGenerationId"])
                failures = [
                    {
                        "githubRepositoryId": item.candidate.githubRepositoryId,
                        "repository": item.candidate.repository,
                        "reason": item.failureCode or "incomplete",
                    }
                    for item in artifact.assessments
                    if item.gate is None or item.copyFailureCode
                ]
                completed = [
                    item.candidate.githubRepositoryId
                    for item in artifact.assessments
                    if item.gate is not None and not item.valueFailureCode and not item.copyFailureCode
                ]
            operation.update(
                status="failed"
                if result.get("status") == "degraded"
                else ("completed" if result["publishedCount"] else "empty"),
                completedAt=datetime.now(UTC).isoformat(),
                providerCalls=ledger.snapshot()["attempted"],
                result={
                    "processedCount": len(plan["candidates"]),
                    "publishedCount": result["publishedCount"],
                    "failedCount": len(failures),
                    "failures": failures,
                    "completedCandidateIds": completed,
                    "cacheHits": result.get("cacheHits", 0),
                    "generationId": result.get("selectionGenerationId"),
                    "installed": result.get("changed", False),
                    "stopped": result.get("stopped", False),
                    "stopReason": result.get("stopReason"),
                },
            )
            atomic(path, operation)
    except BaseException as exc:
        if operation:
            code = getattr(exc, "code", None)
            safe_code = (
                code
                if isinstance(code, str)
                and re.fullmatch(r"(?:rardar_selection|provider_budget|provider_operation)_[a-z0-9_]{1,80}", code)
                else "discover_operation_failed"
            )
            operation.update(
                status="interrupted" if isinstance(exc, asyncio.CancelledError) else "failed",
                completedAt=datetime.now(UTC).isoformat(),
                errorCode=safe_code,
            )
            atomic(path, operation)
        if not ready.done():
            ready.set_exception(ValueError("discover_plan_changed_or_unavailable"))
        if isinstance(exc, asyncio.CancelledError):
            raise
