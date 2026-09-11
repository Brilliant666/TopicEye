"""Rardar's dual-board Today and bounded historical reading over shared materials."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx

from app.core.config import settings
from app.integrations.rardar.profile_cache_v2 import ProfileStoreEnvelopeV2, _read_plain
from app.integrations.rardar.project_identity import canonical_repository, project_id_for_repository
from app.integrations.rardar.serving_profiles import _digest, collect_official_project_profile
from app.integrations.rardar.serving_schemas import OfficialProjectProfile, ProjectEvidenceProjection
from app.integrations.rardar.trending_store import (
    apply_materials,
    historical_snapshot,
    load_snapshot,
    publish_sources,
    read_json,
)
from app.services.llm.provider_budget import ProviderBudgetError, atomic, file_lock, plain


def project_material(profile, evidence, *, source_kind: str = "profile_cache", metadata=None) -> dict:
    """Expose only the original, validated evidence-bound saved interpretation.

    No rebinding of old source revision/date, Star or ranking to a new board.
    A malformed enhancement is omitted at build time, never downgraded while
    reading an already published snapshot with a bad hash.
    """
    repository = canonical_repository(profile.repository)
    if (
        str(profile.htmlUrl).rstrip("/").lower() != f"https://github.com/{repository}"
        or evidence.repository != profile.repository
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
    # Every restored semantic layer keeps the existing Serving evidence rules;
    # a title/shape alone is not proof that its claim is grounded.
    claims = [
        x
        for x in [
            summary,
            positioning,
            profile.officialTaglineZh,
            profile.officialPositioningZh,
            profile.coreValueZh,
            profile.rardarAssessmentZh,
            *capabilities,
            *profile.capabilityBulletsZh,
            *profile.productFormsZh,
            *profile.supportedEnvironmentsZh,
            *profile.primaryUseCasesZh,
            *profile.deliveryFormsZh,
            *(item.titleZh for item in profile.officialHighlights),
            *(item.detailZh for item in profile.officialHighlights),
            *(item.detail for item in profile.keyDifferentiators),
            *(item.detail for item in profile.rardarDifferentiators),
        ]
        if x
    ]
    if any(
        not profile.claimEvidenceRefs.get(claim) or not set(profile.claimEvidenceRefs[claim]) <= allowed
        for claim in claims
    ):
        raise ValueError("historical_profile_reference_invalid")
    reference_groups = [
        *profile.claimEvidenceRefs.values(),
        profile.coreValueEvidenceRefs,
        profile.officialTaglineEvidenceRefs,
        profile.officialPositioningEvidenceRefs,
        profile.positioningEvidenceRefs,
        profile.rardarAssessmentEvidenceRefs,
        *(x.evidenceRefs for x in profile.capabilities),
        *(x.evidenceRefs for x in profile.keyDifferentiators),
        *(x.evidenceRefs for x in profile.rardarDifferentiators),
        *(x.evidenceRefs for x in profile.officialHighlights),
        *(x.evidenceRefs for x in profile.positioningExcludedClauses),
        *(x.evidenceRefs for x in profile.selectedSections),
    ]
    if any(not set(refs) <= allowed for refs in reference_groups):
        raise ValueError("historical_profile_reference_invalid")
    if (
        profile.readmePath != evidence.readmePath
        or profile.readmeBlobSha != evidence.readmeBlobSha
        or profile.selectedSections != evidence.selectedSections
        or profile.originalExcerpts != evidence.originalExcerpts
    ):
        raise ValueError("historical_profile_binding_invalid")
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
        "repository": repository,
        "materialState": "complete" if summary and positioning and capabilities else "partial",
        "displayProfile": profile.model_dump(mode="json"),
        "displayEvidence": evidence.model_dump(mode="json"),
        "material": {
            "schemaVersion": 2,
            "sourceKind": source_kind,
            "sourceGeneration": profile.generationId,
            "sourceRevision": evidence.digest,
            "generatedAt": profile.generatedAt.isoformat(),
        },
        "productForms": profile.productFormsZh,
        "runtimeEnvironments": profile.supportedEnvironmentsZh,
        "artifactTypes": profile.deliveryFormsZh,
        **(
            {
                "language": metadata.primaryLanguage,
                "topics": metadata.topics,
                "license": metadata.licenseSpdxId,
                "pushedAt": metadata.pushedAt.isoformat() if metadata.pushedAt else None,
            }
            if metadata is not None
            else {}
        ),
        "profile": {
            "summary": summary,
            "positioning": positioning,
            "capabilities": capabilities,
            "useCases": profile.primaryUseCasesZh,
            # The original Profile has no generic limitations array. Absence
            # is unknown; real assessment/excluded clauses stay in displayProfile.
            "limitations": None,
            "startHere": links,
            "sourceLabel": profile.sourceLabel,
            "sourceUrl": f"https://github.com/{repository}",
            "generatedAt": profile.generatedAt.isoformat(),
            "sourceRevision": evidence.digest,
            "sourceGeneration": profile.generationId,
            "evidenceRefs": sorted({r for c in claims for r in profile.claimEvidenceRefs[c]}),
        },
    }


def _retained_serving_details(target: Path):
    """Enumerate only source-indexed publications through the original loader."""
    from app.integrations.rardar.serving import ServingProjectionLoader

    loader = ServingProjectionLoader(target)
    # Only retained, validated source pointers are an archive index. Do not
    # accept arbitrary orphan project files or reconstruct a trusted pointer.
    sources = target / "serving" / "sources"
    plain(sources, missing=True)
    generations = [None, *(p.stem for p in sorted(sources.glob("*.json")) if sources.exists())]
    visited = set()
    for generation in generations:
        try:
            snapshot, _ = loader.load_today_with_etag(generation)
            if snapshot.servingGenerationId in visited:
                continue
            visited.add(snapshot.servingGenerationId)
            for row in snapshot.exactRanked:
                try:
                    detail, _ = loader.load_project_with_etag(row.githubRepositoryId, snapshot.generationId)
                    yield detail
                except (ValueError, OSError, RuntimeError):
                    continue
        except (ValueError, OSError, RuntimeError):
            pass


def saved_materials(target: Path) -> dict:
    found, times = {}, {}

    def remember(profile, evidence, *, source_kind="profile_cache", metadata=None):
        material = project_material(profile, evidence, source_kind=source_kind, metadata=metadata)
        key = canonical_repository(profile.repository)
        # storedAt can change during cache migration, so it must not make an
        # older interpretation replace a newer one. Do not rewrite either date.
        version = (profile.generatedAt, evidence.digest)
        if key not in times or version > times[key]:
            previous = found.get(key, {})
            if previous.get("githubRepositoryId") == profile.githubRepositoryId:
                material = {
                    **{k: previous[k] for k in ("language", "topics", "license", "pushedAt") if k in previous},
                    **material,
                }
            found[key], times[key] = material, version

    # Published v8/legacy projections remain readable through their existing
    # validators even when an older cache-envelope schema is no longer current.
    for detail in _retained_serving_details(target):
        try:
            remember(detail.profile, detail.evidence, source_kind="published_serving", metadata=detail.project)
        except (ValueError, OSError, RuntimeError):
            continue
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
                    remember(record.profile, record.evidence)
                except (ValueError, TypeError, OSError):
                    continue  # invalid optional cache is never installed as healthy content
    return found


def _history_with_materials(target: Path, materials: dict) -> dict:
    snapshot = historical_snapshot(target, materials=materials)
    projects = {project["repository"]: project for project in snapshot["projects"]}
    seen = set()
    for detail in _retained_serving_details(target):
        fact = detail.project
        repository = canonical_repository(fact.repository)
        existing = projects.get(repository)
        if existing and existing.get("githubRepositoryId") not in (None, fact.githubRepositoryId):
            continue
        key = (repository, fact.windowStartedAt, fact.windowEndedAt)
        if key in seen:
            continue  # same fact generation can have several material rebuilds
        seen.add(key)
        project = projects.setdefault(
            repository,
            {
                "repository": repository,
                "repositoryUrl": str(fact.htmlUrl),
                "projectId": project_id_for_repository(repository),
                "githubRepositoryId": fact.githubRepositoryId,
                "description": fact.description,
                "totalStars": fact.totalStars,
                "appearances": [],
                "dualListed": False,
                "materialState": "unavailable",
                "profile": None,
                "historyAppearances": 0,
                # The observation window is historical fact time, not the
                # time this machine first downloaded the old publication.
                "firstSeenAt": None,
                "lastSeenAt": None,
            },
        )
        project.setdefault("historicalRardarEvidence", []).append(
            {
                "source": "rardar_today",
                "sourceGeneration": detail.generationId,
                "servingGeneration": detail.servingGenerationId,
                "rank": fact.rank,
                "windowStartedAt": fact.windowStartedAt.isoformat(),
                "windowEndedAt": fact.windowEndedAt.isoformat(),
                "observedStarDelta": fact.observedStarDelta,
                "totalStars": fact.totalStars,
            }
        )
    for project in projects.values():
        if project.get("historicalRardarEvidence"):
            project["historicalRardarEvidence"].sort(key=lambda item: item["windowEndedAt"], reverse=True)
    snapshot["projects"] = list(projects.values())
    snapshot = apply_materials(snapshot, materials)
    snapshot["projects"].sort(key=lambda p: (p["profile"] is None, -(p["totalStars"] or 0), p["repository"]))
    return snapshot


def load_saved_project_profile(
    target: Path, repository: str
) -> tuple[OfficialProjectProfile, ProjectEvidenceProjection] | None:
    """Shared validated material for on-demand explanation, without fact rebinding."""
    material = saved_materials(target).get(canonical_repository(repository))
    if material is None:
        return None
    return (
        OfficialProjectProfile.model_validate_json(json.dumps(material["displayProfile"]), strict=True),
        ProjectEvidenceProjection.model_validate_json(json.dumps(material["displayEvidence"]), strict=True),
    )


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
    target = Path(settings.RARDAR_INTELLIGENCE_DATA_DIR)
    return apply_materials(load_snapshot(target), saved_materials(target))


def history() -> dict:
    target = Path(settings.RARDAR_INTELLIGENCE_DATA_DIR)
    return _history_with_materials(target, saved_materials(target))


def detail(identifier: str, generation: str | None, *, historical: bool = False) -> dict:
    target = Path(settings.RARDAR_INTELLIGENCE_DATA_DIR)
    snapshot = history() if historical else apply_materials(load_snapshot(target, generation), saved_materials(target))
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


async def _collect_project_material(target: Path, project: dict, generation: str, client, route):
    """The shared one-project collector, independent of old Explosion membership."""
    repository = canonical_repository(project["repository"])
    response = await client.get(f"/repos/{repository}")
    response.raise_for_status()
    meta = response.json()
    if (
        not isinstance(meta, dict)
        or not isinstance(meta.get("full_name"), str)
        or type(meta.get("id")) is not int
        or meta["id"] <= 0
        or not isinstance(meta.get("default_branch"), str)
        or not meta["default_branch"]
        or (meta.get("license") is not None and not isinstance(meta["license"], dict))
        or (meta.get("pushed_at") is not None and not isinstance(meta["pushed_at"], str))
    ):
        raise ValueError("repository_metadata_invalid")
    if canonical_repository(meta["full_name"]) != repository or project.get("githubRepositoryId") not in (
        None,
        meta["id"],
    ):
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
        pushedAt=datetime.fromisoformat(meta["pushed_at"].replace("Z", "+00:00")) if meta.get("pushed_at") else None,
    )
    return await collect_official_project_profile(
        facts,
        generation,
        target / "profile-cache",
        client=client,
        translate=True,
        model_route_identity=route,
    )


async def generate_project_material(target: Path, project_id: str) -> dict:
    """Explicit bounded single-item completion over the same daily budget/cache.

    This is not called by GET or board refresh. It fixes membership to a real
    saved current/history project and never creates an additional budget pool.
    """
    from app.services.llm.daily_provider_budget import ProviderWorkYield, daily_execution_budget, work_slice
    from app.services.rardar_daily_operations import operation_root
    from app.services.rardar_llm_control import resolve_rardar_route_identity

    materials = saved_materials(target)
    snapshot = _history_with_materials(target, materials)
    project = next((p for p in snapshot["projects"] if p["projectId"] == project_id), None)
    if project is None:
        raise LookupError("trending_project_not_found")
    if project.get("displayProfile") is not None:
        return {"status": "reused", "projectId": project_id, "providerCalls": 0}
    work = None
    try:
        budget = await daily_execution_budget("rardar_project_profile")
        if budget is None:
            return {"status": "pending", "waitReason": "daily_budget_not_configured", "providerCalls": 0}
        if budget[0].snapshot()["remaining"] <= 0:
            return {"status": "pending", "waitReason": "daily_budget_exhausted", "providerCalls": 0}
        root = operation_root()
        root.mkdir(parents=True, exist_ok=True)
        # The existing operation mutex prevents manual completion racing a
        # scheduled round for the same project while sharing its paid stages.
        with file_lock(root / "writer.lock", blocking=False):
            route = await resolve_rardar_route_identity()
            generation = snapshot["generationId"] or f"historical-material-{_digest(project)[:32]}"
            async with httpx.AsyncClient(
                base_url="https://api.github.com",
                timeout=12,
                follow_redirects=False,
                trust_env=False,
                headers={"User-Agent": "TopicEye-Rardar/2.0"},
            ) as client:
                with work_slice(max_requests=6, background=True) as work:
                    collected = await _collect_project_material(target, project, generation, client, route)
            material = project_material(collected.profile, collected.evidence)
            if collected.profile_cache_state not in {"hit", "rebound", "migrated", "rebuilt"}:
                raise ValueError("historical_profile_not_readable")
            return {
                "status": "reused" if collected.profile_cache_state in {"hit", "rebound", "migrated"} else "processed",
                "projectId": project_id,
                "materialState": material["materialState"],
                "providerCalls": work.used_requests,
                "profileCacheState": collected.profile_cache_state,
            }
    except ProviderWorkYield as exc:
        return {"status": "pending", "waitReason": exc.code, "providerCalls": work.used_requests if work else 0}
    except ProviderBudgetError as exc:
        return {"status": "pending", "waitReason": exc.code, "providerCalls": work.used_requests if work else 0}


async def historical_work(target: Path, progress: dict, save) -> dict:
    """Use the existing Profile collector and daily request lock, never Selection.

    A daily project bound is a configurable work allowance, not a publication
    gate. Resume keeps the same attempt count; good earlier entries stay readable.
    """
    from app.services.llm.daily_provider_budget import ProviderWorkYield, daily_execution_budget, work_slice
    from app.services.rardar_llm_control import resolve_rardar_route_identity

    materials = saved_materials(target)
    snapshot = _history_with_materials(target, materials)
    projects = snapshot["projects"]
    today_repositories = {p["repository"] for p in load_snapshot(target)["projects"]}
    result = {
        "checked": len(projects),
        "reused": sum(p["profile"] is not None for p in projects),
        "processed": 0,
        "refreshed": 0,
        "failed": 0,
        "status": "completed",
        "checkedToday": sum(p["repository"] in today_repositories for p in projects),
        "checkedHistorical": sum(p["repository"] not in today_repositories for p in projects),
    }
    rotation_path = target / "trending-boards" / "material-work.json"
    rotation = read_json(rotation_path) or {}
    checks = rotation.setdefault("_successfulChecks", {})

    def due(project: dict) -> bool:
        profile = project["profile"]
        if profile is None:
            return True
        checked = datetime.fromisoformat(profile["generatedAt"])
        prior = checks.get(project["repository"], {})
        if _digest(profile) in prior.get("profileDigests", []):
            checked = max(checked, datetime.fromisoformat(prior["checkedAt"]))
        return datetime.now(UTC) - checked > timedelta(days=30)

    pending = [p for p in projects if due(p)]
    result["remaining"] = len(pending)
    if not pending:
        return result
    try:
        budget = await daily_execution_budget("rardar_project_profile")
    except ProviderBudgetError as exc:
        if exc.code != "provider_daily_budget_unconfigured":
            raise
        budget = None
    if budget is None:
        return {**result, "status": "pending", "waitReason": "daily_budget_not_configured"}
    ledger = budget[0]
    if ledger.snapshot()["remaining"] <= 0:
        return {**result, "status": "pending", "waitReason": "daily_budget_exhausted"}
    route = await resolve_rardar_route_identity()
    attempts = progress.setdefault("attempts", {})
    limit = settings.RARDAR_HISTORICAL_DAILY_LIMIT
    # Previously failed projects rotate behind never-attempted work, with a
    # daily bounded retry record rather than a permanent negative cache.
    pending.sort(key=lambda p: (rotation.get(p["repository"], ""), -(p["totalStars"] or 0), p["repository"]))
    # Current newcomers and the historical backlog share one collector/cache
    # and one existing daily allowance. Alternate useful work when both have
    # candidates; no source needs to wait for the other inventory to finish.
    queues = {
        "today": [p for p in pending if p["repository"] in today_repositories],
        "historical": [p for p in pending if p["repository"] not in today_repositories],
    }
    scope = rotation.get("_nextMaterialScope", "today")
    if scope not in queues:
        scope = "today"
    pending = []
    while any(queues.values()):
        if not queues[scope]:
            scope = "historical" if scope == "today" else "today"
        pending.append(queues[scope].pop(0))
        scope = "historical" if scope == "today" else "today"
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
            previous_scope = rotation.get("_nextMaterialScope")
            rotation["_nextMaterialScope"] = "historical" if repository in today_repositories else "today"
            rotation[repository] = datetime.now(UTC).isoformat()
            atomic(rotation_path, rotation)
            save()  # durable admission precedes IO/model work, including interruption
            work = None
            try:
                with work_slice(max_requests=6, background=True) as work:
                    collected = await _collect_project_material(
                        target, project, snapshot["generationId"], client, route
                    )
                material = project_material(collected.profile, collected.evidence)
                if collected.profile_cache_state in {"hit", "rebound", "migrated"}:
                    result["refreshed"] += 1
                    if project["profile"] is None:
                        result["reused"] += 1
                elif collected.profile_cache_state == "rebuilt":
                    result["processed"] += 1
                else:
                    raise ValueError("historical_profile_not_readable")
                checks[repository] = {
                    "checkedAt": datetime.now(UTC).isoformat(),
                    # A compatible rebound is not persisted over its immutable
                    # cache envelope. Also bind the saved reading we checked,
                    # without rewriting its source generation or generatedAt.
                    "profileDigests": sorted(
                        {_digest(material["profile"])}
                        | ({_digest(project["profile"])} if project["profile"] is not None else set())
                    ),
                }
                atomic(rotation_path, rotation)
            except ProviderWorkYield as exc:
                if work is not None and work.used_requests == 0:
                    # Release only this provisional admission after a proven
                    # pre-request scheduling wait. Never refund paid stages,
                    # real failures or an interrupted/unknown execution.
                    attempts[repository] -= 1
                    if previous_scope is None:
                        rotation.pop("_nextMaterialScope", None)
                    else:
                        rotation["_nextMaterialScope"] = previous_scope
                    atomic(rotation_path, rotation)
                result.update(status="pending", waitReason=exc.code)
                save()
                break
            except (ValueError, OSError, httpx.HTTPError, ProviderBudgetError):
                result["failed"] += 1
            save()
            await asyncio.sleep(0)
    result["remaining"] = len(pending) - result["processed"] - result["refreshed"]
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
