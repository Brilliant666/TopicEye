"""Rardar's dual-board Today and bounded historical reading over shared materials."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx

from app.core.config import settings
from app.integrations.rardar.profile_cache_v2 import ProfileStoreEnvelopeV2, _read_plain
from app.integrations.rardar.project_identity import canonical_repository
from app.integrations.rardar.serving_profiles import _digest, collect_official_project_profile
from app.integrations.rardar.trending_store import historical_snapshot, load_snapshot, publish_sources, read_json
from app.services.llm.provider_budget import ProviderBudgetError, atomic, file_lock, plain


def project_material(profile, evidence) -> dict:
    """Expose only the original, validated evidence-bound saved interpretation.

    No rebinding of old source revision/date, Star or ranking to a new board.
    A malformed enhancement is omitted at build time, never downgraded while
    reading an already published snapshot with a bad hash.
    """
    repository = canonical_repository(profile.repository)
    if (
        evidence.repository != profile.repository
        or evidence.githubRepositoryId != profile.githubRepositoryId
        or evidence.generationId != profile.generationId
        or profile.evidenceDigest != evidence.digest
        or _digest(evidence.model_dump(mode="json", exclude={"digest"})) != evidence.digest
    ):
        raise ValueError("historical_profile_binding_invalid")
    allowed = set(evidence.evidenceIndex)
    summary = profile.identitySummaryZh or profile.officialSummaryZh
    positioning = profile.positioningZh or profile.officialPositioningZh
    capabilities = [x.detail for x in profile.capabilities]
    claims = [x for x in [summary, positioning, *capabilities, *profile.primaryUseCasesZh] if x]
    if any(
        not profile.claimEvidenceRefs.get(claim) or not set(profile.claimEvidenceRefs[claim]) <= allowed
        for claim in claims
    ):
        raise ValueError("historical_profile_reference_invalid")
    if any(not set(x.evidenceRefs) <= allowed for x in profile.capabilities):
        raise ValueError("historical_profile_reference_invalid")
    links = []
    for link in profile.startHere:
        url = str(link.htmlUrl)
        if (
            not url.lower().startswith(f"https://github.com/{repository}/")
            or not set(link.evidenceRefs) <= allowed
            or not any(evidence.pathRefs.get(ref) == link.path for ref in link.evidenceRefs)
        ):
            raise ValueError("historical_profile_link_invalid")
        links.append({"label": link.label, "url": url})
    if profile.qualityState == "rejected" or profile.translationState == "unavailable" or not summary:
        raise ValueError("historical_profile_not_readable")
    return {
        "githubRepositoryId": profile.githubRepositoryId,
        "materialState": "complete" if summary and positioning and capabilities else "partial",
        "profile": {
            "summary": summary,
            "positioning": positioning,
            "capabilities": capabilities,
            "useCases": profile.primaryUseCasesZh,
            "limitations": [],
            "startHere": links,
            "sourceLabel": profile.sourceLabel,
            "sourceUrl": f"https://github.com/{repository}",
            "generatedAt": profile.generatedAt.isoformat(),
            "sourceRevision": evidence.digest,
            "sourceGeneration": profile.generationId,
            "evidenceRefs": sorted({r for c in claims for r in profile.claimEvidenceRefs[c]}),
        },
    }


def saved_materials(target: Path) -> dict:
    found, times = {}, {}
    # Published v8/legacy projections remain readable through their existing
    # validators even when an older cache-envelope schema is no longer current.
    from app.integrations.rardar.serving import ServingProjectionLoader

    for loader, list_method, detail_method, members in (
        (ServingProjectionLoader(target), "load_today_with_etag", "load_project_with_etag", "exactRanked"),
    ):
        try:
            snapshot, _ = getattr(loader, list_method)()
            for row in getattr(snapshot, members):
                try:
                    detail, _ = getattr(loader, detail_method)(row.githubRepositoryId, snapshot.generationId)
                    material = project_material(detail.profile, detail.evidence)
                    key = canonical_repository(detail.profile.repository)
                    found[key], times[key] = material, detail.profile.generatedAt
                except (ValueError, OSError, RuntimeError):
                    continue
        except (ValueError, OSError, RuntimeError):
            pass
    for name in ("profile-cache", "selection-profile-cache"):
        root = target / name / "profile-store" / "v2"
        plain(root, missing=True)
        for directory in sorted(root.iterdir()) if root.exists() else []:
            plain(directory)
            if not directory.is_dir():
                continue
            for path in sorted(directory.glob("*.json")):
                try:
                    raw = _read_plain(path, root=target)
                    record = ProfileStoreEnvelopeV2.model_validate_json(raw, strict=True)
                    if (
                        str(record.cacheIdentity.repositoryId) != directory.name
                        or record.cacheIdentity.identityDigest != path.stem
                    ):
                        raise ValueError("profile_path_identity_invalid")
                    material = project_material(record.profile, record.evidence)
                    repository = canonical_repository(record.profile.repository)
                    if repository not in times or record.storedAt > times[repository]:
                        found[repository], times[repository] = material, record.storedAt
                except (ValueError, TypeError, OSError):
                    continue  # invalid optional cache is never installed as healthy content
    return found


async def refresh_boards(target: Path | None = None) -> dict:
    from app.integrations.rardar.trending_boards import fetch_boards

    if target is None and not settings.RARDAR_INTELLIGENCE_DATA_DIR:
        raise ValueError("rardar_boards_not_configured")
    target = target or Path(settings.RARDAR_INTELLIGENCE_DATA_DIR)
    results = await fetch_boards()
    materials = await asyncio.to_thread(saved_materials, target)
    installed = await asyncio.to_thread(publish_sources, target, results, materials=materials)
    current = load_snapshot(target)
    return {
        **installed,
        "sources": current["sources"],
        "providerCalls": 0,
        "status": "partial"
        if any(x["status"] != "healthy" for x in current["sources"])
        else "updated"
        if installed["changed"]
        else "unchanged",
    }


def today() -> dict:
    return load_snapshot(Path(settings.RARDAR_INTELLIGENCE_DATA_DIR))


def history() -> dict:
    target = Path(settings.RARDAR_INTELLIGENCE_DATA_DIR)
    return historical_snapshot(target, materials=saved_materials(target))


def detail(identifier: str, generation: str | None, *, historical: bool = False) -> dict:
    snapshot = history() if historical else load_snapshot(Path(settings.RARDAR_INTELLIGENCE_DATA_DIR), generation)
    for project in snapshot["projects"]:
        if project["projectId"] == identifier:
            return {
                **project,
                "generationId": snapshot["generationId"],
                "publishedAt": snapshot["publishedAt"],
                "sources": snapshot["sources"],
                "historical": historical,
            }
    raise LookupError("trending_project_not_found")


async def historical_work(target: Path, progress: dict, save) -> dict:
    """Use the existing Profile collector and daily request lock, never Selection.

    A daily project bound is a configurable work allowance, not a publication
    gate. Resume keeps the same attempt count; good earlier entries stay readable.
    """
    from app.services.llm.daily_provider_budget import ProviderWorkYield, daily_execution_budget, work_slice
    from app.services.rardar_llm_control import resolve_rardar_route_identity

    materials = saved_materials(target)
    snapshot = historical_snapshot(target, materials=materials)
    projects = snapshot["projects"]
    result = {
        "checked": len(projects),
        "reused": sum(p["profile"] is not None for p in projects),
        "processed": 0,
        "failed": 0,
        "status": "completed",
    }
    pending = [
        p
        for p in projects
        if p["profile"] is None
        or datetime.now(UTC) - datetime.fromisoformat(p["profile"]["generatedAt"]) > timedelta(days=30)
    ]
    result["remaining"] = len(pending)
    if not pending:
        return result
    budget = await daily_execution_budget("rardar_project_profile")
    if budget is None:
        return {**result, "status": "pending", "waitReason": "daily_budget_not_configured"}
    ledger = budget[0]
    if ledger.snapshot()["remaining"] <= 0:
        return {**result, "status": "pending", "waitReason": "daily_budget_exhausted"}
    route = await resolve_rardar_route_identity()
    attempts = progress.setdefault("attempts", {})
    rotation_path = target / "trending-boards" / "material-work.json"
    rotation = read_json(rotation_path) or {}
    limit = settings.RARDAR_HISTORICAL_DAILY_LIMIT
    # Previously failed projects rotate behind never-attempted work, with a
    # daily bounded retry record rather than a permanent negative cache.
    pending.sort(key=lambda p: (rotation.get(p["repository"], ""), -(p["totalStars"] or 0), p["repository"]))
    async with httpx.AsyncClient(
        base_url="https://api.github.com",
        timeout=12,
        follow_redirects=False,
        trust_env=False,
        headers={"User-Agent": "TopicEye-Rardar/2.0"},
    ) as client:
        for project in pending:
            if sum(attempts.values()) >= limit:
                break
            repository = project["repository"]
            if attempts.get(repository, 0) >= 2:
                continue
            attempts[repository] = attempts.get(repository, 0) + 1
            rotation[repository] = datetime.now(UTC).isoformat()
            atomic(rotation_path, rotation)
            save()  # durable admission precedes IO/model work, including interruption
            try:
                response = await client.get(f"/repos/{repository}")
                response.raise_for_status()
                meta = response.json()
                if canonical_repository(meta["full_name"]) != repository or type(meta["id"]) is not int:
                    raise ValueError("repository_identity_mismatch")
                facts = SimpleNamespace(
                    githubRepositoryId=meta["id"],
                    repository=repository,
                    htmlUrl=f"https://github.com/{repository}",
                    defaultBranch=meta["default_branch"],
                    description=meta.get("description") or "",
                    primaryLanguage=meta.get("language"),
                    topics=meta.get("topics") or [],
                    licenseSpdxId=(meta.get("license") or {}).get("spdx_id"),
                    pushedAt=datetime.fromisoformat(meta["pushed_at"].replace("Z", "+00:00"))
                    if meta.get("pushed_at")
                    else None,
                )
                # Independent repository facts; no dummy rank/delta/window needed
                # by the reused one-project material collector.
                with work_slice(max_requests=6, background=True):
                    collected = await collect_official_project_profile(
                        facts,
                        snapshot["generationId"],
                        target / "profile-cache",
                        client=client,
                        translate=True,
                        model_route_identity=route,
                    )
                project_material(collected.profile, collected.evidence)
                result["processed"] += 1
            except ProviderWorkYield as exc:
                result.update(status="pending", waitReason=exc.code)
                save()
                break
            except (ValueError, OSError, httpx.HTTPError, ProviderBudgetError):
                result["failed"] += 1
            save()
            await asyncio.sleep(0)
    result["remaining"] = len(pending) - result["processed"]
    if result["remaining"] and result["status"] == "completed":
        result.update(status="partial", waitReason="next_daily_work")
    return result


async def run_daily_refocus() -> dict:
    # Reuse the scheduler's existing operation lock and status files. Version the
    # cycle file so an old completed Discover run cannot suppress the new scope.
    from app.services.rardar_daily_operations import ZONE, _execution_paused, _record_interruption, operation_root

    if not settings.RARDAR_INTELLIGENCE_DATA_DIR:
        return {"status": "not_configured", "reason": "data_not_configured"}
    root = operation_root()
    root.mkdir(parents=True, exist_ok=True)
    day = datetime.now(UTC).astimezone(ZONE).date().isoformat()
    path = root / f"{day}-refocus-v1.json"
    try:
        with file_lock(root / "writer.lock", blocking=False), _record_interruption(path):
            state = read_json(path) or {"date": day, "modules": {}, "progress": {}}
            state.update(status="running", startedAt=datetime.now(UTC).isoformat(), scope="refocus-v1")

            def save():
                atomic(path, state)
                atomic(root / "latest.json", {k: v for k, v in state.items() if k != "progress"})

            save()
            modules = state["modules"]
            for name in ("discover", "news_refresh", "news_enhance"):
                modules[name] = {"status": "paused", "reason": "product_scope_paused"}
            try:
                modules["today"] = await refresh_boards()
            except Exception:
                modules["today"] = {"status": "failed", "errorCode": "board_refresh_failed", "oldResultPreserved": True}
            save()
            if await _execution_paused():
                modules["historical_hot"] = {"status": "pending", "waitReason": "administrator_paused"}
            else:
                try:
                    modules["historical_hot"] = await historical_work(
                        Path(settings.RARDAR_INTELLIGENCE_DATA_DIR),
                        state["progress"].setdefault("historical", {}),
                        save,
                    )
                except Exception:
                    modules["historical_hot"] = {"status": "failed", "errorCode": "historical_material_failed"}
            modules["find"] = {"status": "on_demand", "interactivePriority": True}
            state.update(
                status="partial"
                if any(m.get("status") in {"failed", "pending", "partial"} for m in modules.values())
                else "completed",
                completedAt=datetime.now(UTC).isoformat(),
            )
            save()
            return {k: v for k, v in state.items() if k != "progress"}
    except ProviderBudgetError:
        return {"status": "skipped", "reason": "already_running"}
