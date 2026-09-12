"""Two bounded daily opportunities over the existing board/material pipeline.

Per-source receipts precede publication. A manual sync shares these receipts,
but cannot invoke materials or create another automatic opportunity.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

from app.core.config import settings
from app.integrations.rardar.trending_periods import day_plan, due_period, instant, source_period
from app.integrations.rardar.trending_store import SOURCES, load_snapshot, publish_sources, read_json, validate_source
from app.services.llm.provider_budget import ProviderBudgetError, atomic, digest, file_lock, plain

NON_RESUMABLE = {
    "daily_budget_exhausted",
    "daily_budget_not_configured",
    "provider_daily_budget_unconfigured",
    "daily_interactive_reserve",
    "interactive_reserve",
    "interactive_budget_reserved",
    "historical_daily_limit_reached",
    "material_retry_limit_reached",
    "administrator_paused",
    "calendar_day_changed",
}


async def material_budget_available() -> bool:
    """Qualification is read-only: do not initialize or reserve a Provider call."""
    from app.core.database import async_session
    from app.services.llm.daily_provider_budget import daily_budget_status

    async with async_session() as db:
        state = await daily_budget_status(db)
    return bool(state.get("configured") and state.get("remaining", 0) > state.get("interactiveReserve", 0))


def _validate_receipts(cycle: dict) -> None:
    for key, receipt in cycle["sources"].items():
        if key not in SOURCES or receipt.get("result", {}).get("source") != key:
            raise ValueError("daily_source_receipt_identity")
        if receipt.get("status") == "healthy":
            value = receipt["result"]
            if digest(value) != receipt["digest"]:
                raise ValueError("daily_source_receipt_integrity")
            validate_source(value)
            if value.get("targetPeriodDate") != cycle["period"]["sourceDate"]:
                raise ValueError("daily_source_period_mismatch")
            if value.get("acquisitionMode") == "ended_utc_day" and value.get("sourceDate") != value["targetPeriodDate"]:
                raise ValueError("daily_source_period_mismatch")


def _needs_sources(cycle: dict) -> bool:
    return any(
        cycle["sources"].get(key, {}).get("status") != "healthy"
        and cycle["sources"].get(key, {}).get("retryable", True)
        for key in SOURCES
    )


def _needs_publication(cycle: dict) -> bool:
    healthy = {key: r["digest"] for key, r in cycle["sources"].items() if r.get("status") == "healthy"}
    return bool(healthy) and cycle.get("publishedReceipts") != healthy


def _material_pending(day: dict) -> bool:
    result = day.get("materials", {})
    return (
        result.get("status") in {None, "pending", "partial", "interrupted"}
        and result.get("waitReason") not in NON_RESUMABLE
    )


async def run_refresh(target: Path, *, now=None, trigger: str = "manual", material_work=None) -> dict:
    if trigger not in {"manual", "automatic"}:
        raise ValueError("daily_trigger_invalid")
    if trigger == "manual" and material_work is not None:
        raise ValueError("manual_sync_cannot_generate_materials")
    clock = instant(now)
    plan = day_plan(clock)
    root = target.absolute() / "trending-boards" / "daily-refresh"
    plain(root, missing=True)
    root.mkdir(parents=True, exist_ok=True)
    try:
        with file_lock(root / "writer.lock", blocking=False):
            day_path = root / f"day-{plan['runDate']}.json"
            day = read_json(day_path) or {"schemaVersion": 1, "date": plan["runDate"], "rounds": []}
            rounds = day["rounds"]
            if len(rounds) > 2:
                raise ValueError("daily_round_state_invalid")
            active = rounds[-1] if rounds and rounds[-1]["status"] == "running" else None
            if trigger == "automatic":
                if clock < datetime.fromisoformat(plan["mainAt"]):
                    return {"status": "skipped", "reason": "before_daily_window", "providerCalls": 0, "changed": False}
                if not active and len(rounds) == 2:
                    return {"status": "skipped", "reason": "daily_round_limit", "providerCalls": 0, "changed": False}
                if not active and rounds and clock < datetime.fromisoformat(plan["compensationAt"]):
                    return {
                        "status": "skipped",
                        "reason": "waiting_compensation_window",
                        "providerCalls": 0,
                        "changed": False,
                    }
            period = source_period(active["targetSourceDate"]) if active else due_period(clock)
            # A completed main freezes the period for its compensation as well.
            if trigger == "automatic" and rounds:
                period = source_period(rounds[0]["targetSourceDate"])
            cycle_path = root / f"period-{period['sourceDate']}.json"
            cycle = read_json(cycle_path) or {"schemaVersion": 1, "period": period, "sources": {}}
            if cycle["period"]["sourceDate"] != period["sourceDate"]:
                raise ValueError("daily_source_period_mismatch")
            _validate_receipts(cycle)
            if trigger == "automatic" and rounds and not active:
                pending = (
                    _needs_sources(cycle)
                    or _needs_publication(cycle)
                    or (bool(cycle.get("publishedReceipts")) and not cycle.get("metadataComplete", False))
                )
                if not pending and material_work and _material_pending(day):
                    pending = await material_budget_available()
                if not pending:
                    return {
                        "status": "skipped",
                        "reason": "nothing_to_compensate",
                        "providerCalls": 0,
                        "changed": False,
                    }
            if trigger == "automatic" and active is None:
                active = {
                    "kind": "main" if not rounds else "compensation",
                    "status": "running",
                    "targetSourceDate": period["sourceDate"],
                    "startedAt": clock.isoformat(),
                }
                rounds.append(active)
                atomic(day_path, day)  # admission is durable before external IO

            def save_cycle():
                atomic(cycle_path, cycle)

            fetched = []
            from app.integrations.rardar.trending_boards import fetch_board

            for key in SOURCES:
                prior = cycle["sources"].get(key, {})
                if prior.get("status") == "healthy" or not prior.get("retryable", True):
                    continue
                try:
                    result = await fetch_board(key, target_date=period["sourceDate"])
                    if result.get("source") != key:
                        raise ValueError("daily_source_receipt_identity")
                    if result.get("status") == "healthy":
                        validate_source(result)
                        if result.get("targetPeriodDate") != period["sourceDate"]:
                            raise ValueError("daily_source_period_mismatch")
                        if (
                            result.get("acquisitionMode") == "ended_utc_day"
                            and result.get("sourceDate") != period["sourceDate"]
                        ):
                            raise ValueError("daily_source_period_mismatch")
                except Exception:
                    result = {"source": key, "status": "failed", "errorCode": "source_read_or_validation_failed"}
                fetched.append(key)
                result.setdefault("checkedAt", instant(now).isoformat())
                cycle["sources"][key] = {
                    "status": result["status"],
                    "result": result,
                    "digest": digest(result),
                    "checkedAt": result["checkedAt"],
                    "retryable": result.get("retryable", True),
                }
                save_cycle()

            from app.services import rardar_trending as service

            installed = cycle.get("publication", {"changed": False})
            changed = False
            publication_failed = False
            if _needs_publication(cycle) or fetched:
                results = [r["result"] for r in cycle["sources"].values()]
                try:
                    materials = await asyncio.to_thread(service.saved_materials, target)
                    installed = await asyncio.to_thread(publish_sources, target, results, materials=materials)
                    changed = installed["changed"]
                    cycle["publication"] = installed
                    if changed:
                        cycle["metadataComplete"] = False
                        # A recovered source can introduce new projects after
                        # the main's material work was legitimately complete.
                        if day.get("materials", {}).get("status") == "completed":
                            day.pop("materials", None)
                    cycle["publishedReceipts"] = {
                        key: r["digest"] for key, r in cycle["sources"].items() if r["status"] == "healthy"
                    }
                    save_cycle()
                except Exception:
                    publication_failed = True
                    cycle["publicationError"] = "board_publication_failed"
                    save_cycle()
            current = load_snapshot(target)
            if current.get("generationId") and not cycle.get("metadataComplete") and not publication_failed:
                try:
                    cycle["metadata"] = await service.refresh_metadata(target, current["projects"])
                    cycle["metadataComplete"] = True
                    save_cycle()
                except Exception:
                    cycle["metadataError"] = "metadata_refresh_failed"
                    save_cycle()

            material_result = day.get("materials", {})
            run_requests = 0
            if trigger == "automatic" and material_work and current.get("generationId"):
                # A single bounded run advances multiple existing slices. Never
                # busy-loop a cooperative wait or reset a project's retry debit.
                for _ in range(settings.RARDAR_DAILY_MATERIAL_SLICES):
                    if material_result and not _material_pending({"materials": material_result}):
                        break
                    material_result = await material_work()
                    run_requests += material_result.get("providerRequests", 0)
                    day["materials"] = material_result
                    totals = day.setdefault("materialTotals", {})
                    for key in ("processed", "refreshed", "failed", "providerRequests", "visited"):
                        totals[key] = totals.get(key, 0) + material_result.get(key, 0)
                    day["materialSlices"] = day.get("materialSlices", 0) + 1
                    atomic(day_path, day)
                    if material_result.get("status") == "completed":
                        break
                    if material_result.get("waitReason") not in {"next_scheduled_pass", "work_slice_exhausted"}:
                        break
                    if not (material_result.get("visited", 0) or material_result.get("providerRequests", 0)):
                        break
                    await asyncio.sleep(0)

            unfinished = _needs_sources(cycle) or _needs_publication(cycle) or publication_failed
            result = {
                **installed,
                "changed": changed,
                "generationId": current.get("generationId"),
                "count": len(current["projects"]),
                "status": "partial" if unfinished else "updated" if changed else "unchanged",
                "sources": current["sources"],
                "sourceRequests": len(fetched),
                "requestedSources": fetched,
                "targetPeriod": period,
                "trigger": trigger,
                "providerCalls": run_requests,
                "metadata": cycle.get("metadata", {}),
                "oldResultPreserved": bool((publication_failed or unfinished) and current.get("generationId")),
            }
            if trigger == "automatic":
                active.update(status="completed", completedAt=instant(now).isoformat())
                atomic(day_path, day)
                result["automaticRound"] = active["kind"]
                result["materials"] = {**material_result, **day.get("materialTotals", {})}
            return result
    except ProviderBudgetError as exc:
        if exc.code != "provider_budget_busy":
            raise
        return {"status": "skipped", "reason": "already_running", "providerCalls": 0, "changed": False}
