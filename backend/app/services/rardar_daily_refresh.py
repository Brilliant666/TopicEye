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

_AUDIT_COUNTERS = {
    "processed": "processed",
    "refreshed": "refreshed",
    "failedAttempts": "failed",
    "providerRequests": "providerRequests",
    "visited": "visited",
}


def _audit_counts(value: dict) -> dict:
    # Missing metrics are unknown, not evidence of zero work.
    return {label: value.get(key) for label, key in _AUDIT_COUNTERS.items()}


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


def _receipt_healthy(receipt: dict) -> bool:
    if receipt.get("status") != "healthy":
        return False
    value = receipt.get("result", {})
    # Validate old receipts normally, but do not reuse their former homepage
    # fallback as proof that a requested ended day has been acquired.
    return value.get("source") != "trendshift" or (
        value.get("acquisitionMode") == "ended_utc_day" and value.get("sourceDate") == value.get("targetPeriodDate")
    )


def _needs_sources(cycle: dict) -> bool:
    return any(
        not _receipt_healthy(cycle["sources"].get(key, {})) and cycle["sources"].get(key, {}).get("retryable", True)
        for key in SOURCES
    )


def _needs_publication(cycle: dict) -> bool:
    healthy = {key: r["digest"] for key, r in cycle["sources"].items() if _receipt_healthy(r)}
    return bool(healthy) and cycle.get("publishedReceipts") != healthy


def _material_pending(day: dict, qualification: dict | None = None) -> bool:
    result = day.get("materials", {})
    if result.get("status") not in {None, "pending", "partial", "interrupted"}:
        return False
    if result.get("waitReason") in {
        "daily_budget_exhausted",
        "daily_budget_not_configured",
        "provider_daily_budget_unconfigured",
    }:
        scopes = (qualification or {}).get("qualification", {})
        return any(scopes.get(scope, {}).get("zeroModelEligible", 0) > 0 for scope in ("today", "historical"))
    if result.get("waitReason") in {"historical_daily_limit_reached", "material_retry_limit_reached"}:
        scopes = (qualification or result).get("qualification")
        if isinstance(scopes, dict):
            return any(scopes.get(scope, {}).get("admissionEligible", 0) > 0 for scope in ("today", "historical"))
    return result.get("waitReason") not in NON_RESUMABLE


def safe_publish_reading_snapshots(target: Path, views=None) -> dict:
    """Attach local reading publication without changing the source operation's outcome."""
    selected = tuple(views) if views is not None else ("today", "history")
    try:
        from app.services import rardar_trending as service

        result = service.publish_reading_snapshots(target, views=selected)
        if not isinstance(result, dict):
            raise ValueError("reading_snapshot_publication_result_invalid")
        return result
    except Exception:
        return {view: {"status": "failed", "errorCode": "reading_snapshot_publication_failed"} for view in selected}


async def safe_publish_reading_snapshots_async(target: Path, views=None) -> dict:
    """Keep local card building off the event loop, with the same non-blocking failure boundary."""
    try:
        return await asyncio.to_thread(safe_publish_reading_snapshots, target, views=views)
    except Exception:
        selected = tuple(views) if views is not None else ("today", "history")
        return {view: {"status": "failed", "errorCode": "reading_snapshot_publication_failed"} for view in selected}


def record_reading_publication(target: Path, publication: dict, *, now=None) -> dict:
    """Merge a manual publication receipt into the existing day ledger without waiting."""
    result = {"status": "failed", "errorCode": "reading_publication_receipt_failed"}
    try:
        run_date = day_plan(instant(now))["runDate"]
        result["date"] = run_date
        if (
            not isinstance(publication, dict)
            or not publication
            or any(
                view not in {"today", "history"}
                or not isinstance(value, dict)
                or value.get("status") not in {"published", "reused", "failed"}
                for view, value in publication.items()
            )
        ):
            raise ValueError("reading_publication_receipt_invalid")
        root = target.absolute() / "trending-boards" / "daily-refresh"
        plain(root, missing=True)
        root.mkdir(parents=True, exist_ok=True)
        with file_lock(root / "writer.lock", blocking=False):
            path = root / f"day-{run_date}.json"
            day = read_json(path)
            if day is None:
                day = {"schemaVersion": 1, "date": run_date, "rounds": []}
            if (
                day.get("schemaVersion") != 1
                or day.get("date") != run_date
                or not isinstance(day.get("rounds"), list)
                or not isinstance(day.get("readingPublication", {}), dict)
            ):
                raise ValueError("reading_publication_day_invalid")
            day["readingPublication"] = {**day.get("readingPublication", {}), **publication}
            atomic(path, day)
        return {"status": "saved", "date": run_date}
    except ProviderBudgetError as exc:
        if exc.code == "provider_budget_busy":
            return {**result, "status": "busy", "errorCode": "reading_publication_receipt_busy"}
        return result
    except Exception:
        return result


async def record_reading_publication_async(target: Path, publication: dict, *, now=None) -> dict:
    """Record only the supplied receipt; no publication, source or budget work is started."""
    try:
        return await asyncio.to_thread(record_reading_publication, target, publication, now=now)
    except Exception:
        return {"status": "failed", "errorCode": "reading_publication_receipt_failed"}


def _reading_pending(day: dict) -> tuple[str, ...]:
    publication = day.get("readingPublication", {})
    return tuple(view for view in ("today", "history") if publication.get(view, {}).get("status") == "failed")


async def run_refresh(
    target: Path,
    *,
    now=None,
    trigger: str = "manual",
    material_work=None,
    review_work=None,
    material_qualification=None,
) -> dict:
    if trigger not in {"manual", "automatic"}:
        raise ValueError("daily_trigger_invalid")
    if trigger == "manual" and (
        material_work is not None or review_work is not None or material_qualification is not None
    ):
        raise ValueError("manual_sync_cannot_generate_materials")
    clock = instant(now)
    plan = day_plan(clock)
    root = target.absolute() / "trending-boards" / "daily-refresh"
    plain(root, missing=True)
    root.mkdir(parents=True, exist_ok=True)
    reading_publication = {}
    attempted_reading = set()

    async def publish_reading(views=None):
        publication = await safe_publish_reading_snapshots_async(target, views=views)
        reading_publication.update(publication)
        attempted_reading.update(publication)
        # Persist before another stage can fail or a manual run can return.
        # This uses the daily writer lock already held by run_refresh.
        day["readingPublication"] = dict(reading_publication)
        atomic(day_path, day)

    try:
        with file_lock(root / "writer.lock", blocking=False):
            day_path = root / f"day-{plan['runDate']}.json"
            day = read_json(day_path) or {"schemaVersion": 1, "date": plan["runDate"], "rounds": []}
            reading_publication.update(day.get("readingPublication", {}))
            rounds = day["rounds"]
            if len(rounds) > 2:
                raise ValueError("daily_round_state_invalid")
            active = rounds[-1] if rounds and rounds[-1]["status"] == "running" else None
            resumed_round = active is not None
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
            qualification = None
            if (
                trigger == "automatic"
                and material_work
                and material_qualification
                and day.get("materials", {}).get("waitReason")
                in {
                    "historical_daily_limit_reached",
                    "material_retry_limit_reached",
                    "daily_budget_exhausted",
                    "daily_budget_not_configured",
                    "provider_daily_budget_unconfigured",
                }
            ):
                # Read current saved materials and original per-project daily
                # debits, not yesterday's/earlier slice's aggregate stop reason.
                qualification = await material_qualification()
                day["materialQualification"] = {
                    "checkedAt": clock.isoformat(),
                    "scopes": qualification.get("qualification"),
                }
                atomic(day_path, day)
            if trigger == "automatic" and rounds and not active:
                material_budget_wait = False
                pending = (
                    _needs_sources(cycle)
                    or _needs_publication(cycle)
                    or (bool(cycle.get("publishedReceipts")) and not cycle.get("metadataComplete", False))
                    or (review_work is not None and day.get("historyReview", {}).get("status") != "published")
                    or day.get("historyMetadata", {}).get("status") in {"partial", "failed"}
                    or bool(_reading_pending(day))
                )
                if not pending and material_work and _material_pending(day, qualification):
                    scopes = (qualification or {}).get("qualification", {})
                    zero_model = any(
                        scopes.get(scope, {}).get("zeroModelEligible", 0) > 0 for scope in ("today", "historical")
                    )
                    pending = zero_model or await material_budget_available()
                    material_budget_wait = not pending
                if not pending:
                    return {
                        "status": "skipped",
                        "reason": "material_budget_unavailable_or_interactive_reserved"
                        if material_budget_wait
                        else "nothing_to_compensate",
                        "providerCalls": 0,
                        "changed": False,
                        "materialQualification": qualification.get("qualification") if qualification else None,
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

            if trigger == "automatic" and review_work is not None:
                try:
                    # Local history is independent of today's source health and
                    # Provider allowance. The persisted daily IDs decide reuse.
                    review = await review_work(clock, active["kind"])
                    day["historyReview"] = {"status": "published", **review}
                except Exception:
                    day["historyReview"] = {"status": "failed", "errorCode": "history_review_publication_failed"}
                atomic(day_path, day)
                if day["historyReview"]["status"] == "published":
                    await publish_reading(("history",))

            from app.services import rardar_trending as service

            if trigger == "automatic" and day.get("historyMetadata", {}).get("status") != "completed":
                try:
                    day["historyMetadata"] = await service.refresh_history_metadata(target, clock)
                except Exception as exc:
                    day["historyMetadata"] = {"status": "failed", "errorType": type(exc).__name__, "providerCalls": 0}
                atomic(day_path, day)
                await publish_reading(("history",))

            def save_cycle():
                atomic(cycle_path, cycle)

            fetched = []
            from app.integrations.rardar.trending_boards import fetch_board

            for key in SOURCES:
                prior = cycle["sources"].get(key, {})
                if _receipt_healthy(prior) or not prior.get("retryable", True):
                    continue
                try:
                    result = await fetch_board(key, target_date=period["sourceDate"])
                    if result.get("source") != key:
                        raise ValueError("daily_source_receipt_identity")
                    if result.get("status") == "healthy":
                        validate_source(result)
                        if not _receipt_healthy({"status": "healthy", "result": result}):
                            result = {**result, "status": "failed", "errorCode": "trendshift_target_day_unverified"}
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
                            atomic(day_path, day)
                    cycle["publishedReceipts"] = {
                        key: r["digest"] for key, r in cycle["sources"].items() if _receipt_healthy(r)
                    }
                    save_cycle()
                except Exception:
                    publication_failed = True
                    cycle["publicationError"] = "board_publication_failed"
                    save_cycle()
                # Source health may change even when the fact generation does not.
                # Publish fact-first cards before metadata or Profile work starts.
                await publish_reading()
            current = load_snapshot(target)
            if current.get("generationId") and not cycle.get("metadataComplete") and not publication_failed:
                try:
                    cycle["metadata"] = await service.refresh_metadata(
                        target, service.today_candidates(target)["projects"]
                    )
                    cycle["metadataComplete"] = not (
                        cycle["metadata"].get("failed") or cycle["metadata"].get("pending")
                    )
                    save_cycle()
                except Exception:
                    cycle["metadataError"] = "metadata_refresh_failed"
                    save_cycle()
                await publish_reading()

            if changed and trigger == "automatic" and material_work and material_qualification:
                # A recovered source may add Today projects after the initial
                # eligibility check. Re-read the installed scope, never reuse
                # the old board's empty admission set to suppress those gaps.
                qualification = await material_qualification()
                day["materialQualification"] = {
                    "checkedAt": instant(now).isoformat(),
                    "scopes": qualification.get("qualification"),
                }
                atomic(day_path, day)
            material_result = day.get("materials", {})
            run_requests = 0
            audit_counts = dict.fromkeys(_AUDIT_COUNTERS, 0)
            audit_slices = 0
            if trigger == "automatic" and material_work and current.get("generationId"):
                # A single bounded run advances multiple existing slices. Never
                # busy-loop a cooperative wait or reset a project's retry debit.
                for _ in range(settings.RARDAR_DAILY_MATERIAL_SLICES):
                    if material_result and not _material_pending({"materials": material_result}, qualification):
                        break
                    qualification = None
                    material_result = await material_work()
                    audit_slices += 1
                    for label, key in _AUDIT_COUNTERS.items():
                        value = material_result.get(key)
                        previous = audit_counts[label]
                        audit_counts[label] = previous + value if type(previous) is int and type(value) is int else None
                    run_requests += material_result.get("providerRequests", 0)
                    day["materials"] = material_result
                    totals = day.setdefault("materialTotals", {})
                    for key in ("processed", "refreshed", "failed", "providerRequests", "visited"):
                        totals[key] = totals.get(key, 0) + material_result.get(key, 0)
                    day["materialSlices"] = day.get("materialSlices", 0) + 1
                    atomic(day_path, day)
                    await publish_reading()
                    if material_result.get("status") == "completed":
                        break
                    if material_result.get("waitReason") not in {"next_scheduled_pass", "work_slice_exhausted"}:
                        break
                    if not (material_result.get("visited", 0) or material_result.get("providerRequests", 0)):
                        break
                    await asyncio.sleep(0)

            pending_reading = tuple(view for view in _reading_pending(day) if view not in attempted_reading)
            if pending_reading:
                # A failed local snapshot alone must get the existing 11:00
                # opportunity, without reopening sources or Provider work.
                await publish_reading(pending_reading)
            unfinished = _needs_sources(cycle) or _needs_publication(cycle) or publication_failed
            source_status = "partial" if unfinished else "updated" if changed else "unchanged"
            today_reading = reading_publication.get("today", {})
            reading_failed = today_reading.get("status") == "failed"
            result = {
                **installed,
                "changed": changed,
                "generationId": current.get("generationId"),
                "count": len(current["projects"]),
                "status": "partial" if reading_failed else source_status,
                "sourceStatus": source_status,
                "sources": current["sources"],
                "sourceRequests": len(fetched),
                "requestedSources": fetched,
                "targetPeriod": period,
                "trigger": trigger,
                "providerCalls": run_requests,
                "metadata": cycle.get("metadata", {}),
                "historyMetadata": day.get("historyMetadata", {}),
                "oldResultPreserved": bool((publication_failed or unfinished) and current.get("generationId")),
                "readingPublication": reading_publication,
            }
            if reading_publication:
                result["readingReceipt"] = {"status": "saved", "date": plan["runDate"]}
            if today_reading.get("status") in {"published", "reused", "failed"}:
                result["readingStatus"] = today_reading["status"]
                result["readingDisplay"] = "previous" if reading_failed else "current"
            if reading_failed:
                result["readingNote"] = "公开Today成品发布失败，当前展示未替换；事实同步结果单独保留。"
            elif reading_publication.get("history", {}).get("status") == "failed":
                result["readingNote"] = "Today展示不受影响；历史回顾成品发布失败，历史展示未替换。"
            if trigger == "automatic":
                result["auditRound"] = {
                    "schemaVersion": 1,
                    "roundKind": active["kind"],
                    "resumedRound": resumed_round,
                    "counterScope": "current_invocation",
                    "date": day["date"],
                    "targetSourceDate": period["sourceDate"],
                    "generationId": current.get("generationId"),
                    "sourceRequests": len(fetched),
                    "requestedSources": fetched,
                    "materials": {
                        # This invocation only; not reconstructed from a later queue.
                        "round": audit_counts,
                        "slices": audit_slices,
                        "sliceLimit": settings.RARDAR_DAILY_MATERIAL_SLICES,
                        "cumulative": {
                            key: value if audit_counts[key] is not None else None
                            for key, value in _audit_counts(day.get("materialTotals", {})).items()
                        },
                        "snapshot": {
                            key: material_result.get(key)
                            for key in (
                                "reused",
                                "todayPending",
                                "historicalPending",
                                "remaining",
                                "status",
                                "waitReason",
                                "qualification",
                                "contentRetryDeferred",
                            )
                        },
                    },
                }
                active.update(status="completed", completedAt=instant(now).isoformat())
                atomic(day_path, day)
                result["automaticRound"] = active["kind"]
                result["materials"] = {**material_result, **day.get("materialTotals", {})}
                if review_work is not None:
                    result["historyReview"] = day.get("historyReview")
            return result
    except ProviderBudgetError as exc:
        if exc.code != "provider_budget_busy":
            raise
        return {"status": "skipped", "reason": "already_running", "providerCalls": 0, "changed": False}
