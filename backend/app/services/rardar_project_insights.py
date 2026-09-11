"""Shared, on-demand insights over validated Today/history project materials.

This is an adapter to the existing single-project evidence/model flow, not a
second Profile or task pipeline. Only a successful, revalidated public result
is stored. Reads never collect evidence or invoke a model.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from app.core.config import settings
from app.integrations.rardar.project_identity import canonical_repository
from app.integrations.rardar.serving_schemas import OfficialProjectProfile, ProjectEvidenceProjection
from app.integrations.rardar.trending_store import read_json
from app.schemas.rardar_product import (
    ProjectExplanationRequest,
    ProjectExplanationResponse,
    SharedProjectInsightRequest,
    SharedProjectInsightStatus,
)
from app.services.llm.daily_provider_budget import ProviderWorkYield
from app.services.llm.provider_budget import ProviderBudgetError, atomic, digest, file_lock, plain
from app.services.rardar_llm_control import RardarLLMError, resolve_rardar_route_identity
from app.services.rardar_product import (
    _PROJECT_PROMPT_VERSION,
    _PROJECT_SCHEMA_VERSION,
    _explain_project_with_evidence,
    _static_project_evidence,
    _validate_project_insight,
)
from app.services.rardar_project_evidence import (
    ProjectEvidence,
    collect_project_evidence,
    read_saved_project_evidence,
)

_RUNNING: dict[tuple[str, str], asyncio.Task] = {}
_LAST_STATE: dict[tuple[str, str], SharedProjectInsightStatus] = {}


def _project(identifier: str, request: SharedProjectInsightRequest) -> dict:
    from app.services.rardar_trending import detail

    # Snapshot membership is validated by the same detail path used for reading.
    return detail(identifier, request.generationId, historical=request.context == "historical_hot")


def _facts(project: dict) -> dict:
    return {key: project.get(key) for key in ("description", "pushedAt", "licenseSpdxId")}


def _without_observation_context(value):
    # Strip only known projection provenance locations. Recursively stripping
    # names like "rank" or "digest" could remove an evidence-index entry or a
    # README's actual structured material and wrongly reuse its old analysis.
    projection_fields = {
        "generationId",
        "generatedAt",
        "capturedAt",
        "fetchedAt",
        "observedAt",
        "digest",
        "evidenceDigest",
        "totalStars",
        "stars",
        "rank",
        "observedStarDelta",
        "reportedDelta",
    }
    payload = {key: item for key, item in value.items() if key not in projection_fields}
    profile = payload.get("officialProfile")
    if isinstance(profile, dict):
        payload["officialProfile"] = {
            key: item for key, item in profile.items() if key not in {"generationId", "generatedAt", "evidenceDigest"}
        }
    return payload


def _material_evidence(project: dict, *, read_only: bool = False) -> ProjectEvidence | None:
    if project.get("displayProfile") and project.get("displayEvidence"):
        profile = OfficialProjectProfile.model_validate_json(json.dumps(project["displayProfile"]), strict=True)
        projection = ProjectEvidenceProjection.model_validate_json(json.dumps(project["displayEvidence"]), strict=True)
        # detail() only exports profiles after source/identity/ref validation.
        evidence = _static_project_evidence(SimpleNamespace(profile=profile, evidence=projection))
    else:
        # A saved interpretation remains readable with its original evidence;
        # an explicit new generation still uses the collector's normal TTL.
        evidence = read_saved_project_evidence(project["repository"], _facts(project), allow_stale=read_only)
    return _stable_evidence(evidence) if evidence else None


def _stable_evidence(evidence: ProjectEvidence) -> ProjectEvidence:
    payload = _without_observation_context(evidence.payload)
    return replace(evidence, payload=payload, digest=digest(payload))


def _directory(project: dict) -> Path:
    # Do not accept a path from the client. The canonical repository is hashed.
    repository = canonical_repository(project["repository"])
    path = Path(settings.RARDAR_INTELLIGENCE_DATA_DIR) / "project-insights" / digest(repository)
    try:
        plain(path, missing=True)
    except ProviderBudgetError:
        raise ValueError("project_insight_storage_invalid") from None
    return path


async def _cache_path(project: dict, evidence: ProjectEvidence) -> Path:
    try:
        route = await resolve_rardar_route_identity()
    except RardarLLMError:
        raise
    except Exception:
        # Route lookup is a local configuration read. Unexpected DB/config
        # failures are not model failures and must not expose their raw details.
        raise RardarLLMError("project_insight_route_unavailable") from None
    identity = {
        "repository": canonical_repository(project["repository"]),
        "material": evidence.digest,
        "prompt": _PROJECT_PROMPT_VERSION,
        "schema": _PROJECT_SCHEMA_VERSION,
        "route": route,
    }
    return _directory(project) / f"{digest(identity)}.json"


def _read_result(path: Path, project: dict, evidence: ProjectEvidence) -> ProjectExplanationResponse | None:
    try:
        stored = read_json(path, maximum=150_000)
        if not stored or stored.get("schemaVersion") != 1:
            return None
        payload = stored.get("result")
        if stored.get("digest") != digest(payload):
            return None
        result = ProjectExplanationResponse.model_validate_json(json.dumps(payload), strict=True)
        if (
            result.state != "ready"
            or canonical_repository(result.repository) != canonical_repository(project["repository"])
            or result.evidenceDigest != evidence.digest
            or result.promptVersion != _PROJECT_PROMPT_VERSION
            or result.schemaVersion != _PROJECT_SCHEMA_VERSION
            or (
                project.get("githubRepositoryId") is not None
                and result.githubRepositoryId != project["githubRepositoryId"]
            )
        ):
            return None
        _validate_project_insight(result.analysis, evidence)
        return result.model_copy(update={"cacheHit": True})
    except (ValueError, TypeError, KeyError, OSError, RardarLLMError, ProviderBudgetError):
        return None


def _key(project: dict) -> tuple[str, str]:
    return str(_directory(project).parent), canonical_repository(project["repository"])


async def read_project_insight(identifier: str, request: SharedProjectInsightRequest) -> SharedProjectInsightStatus:
    project = await asyncio.to_thread(_project, identifier, request)
    key = _key(project)
    if key in _RUNNING:
        return SharedProjectInsightStatus(state="running")
    try:
        evidence = _material_evidence(project, read_only=True)
    except (ValueError, TypeError, OSError, ProviderBudgetError):
        return SharedProjectInsightStatus(state="unavailable", errorCode="project_insight_material_invalid")
    if evidence:
        try:
            saved = _read_result(await _cache_path(project, evidence), project, evidence)
            if saved:
                return SharedProjectInsightStatus(state="ready", result=saved)
        except RardarLLMError as exc:
            return SharedProjectInsightStatus(state="unavailable", errorCode=exc.code)
    last = _LAST_STATE.get(key)
    return last if last and last.state != "ready" else SharedProjectInsightStatus(state="unprocessed")


async def _execute(project: dict, request: SharedProjectInsightRequest) -> SharedProjectInsightStatus:
    directory = _directory(project)
    directory.mkdir(parents=True, exist_ok=True)
    try:
        # Duplicate processes cannot spend on the same project simultaneously.
        with file_lock(directory / "execution.lock", blocking=False):
            evidence = _material_evidence(project)
            if evidence is None:
                evidence = _stable_evidence(await collect_project_evidence(project["repository"], _facts(project)))
            if not evidence.path_refs:
                return SharedProjectInsightStatus(state="unavailable", errorCode="project_evidence_incomplete")
            path = await _cache_path(project, evidence)
            saved = _read_result(path, project, evidence)
            if saved:
                return SharedProjectInsightStatus(state="ready", result=saved)
            result = await _explain_project_with_evidence(
                ProjectExplanationRequest(repository=project["repository"], generationId=project["generationId"]),
                evidence,
                github_repository_id=project.get("githubRepositoryId"),
            )
            if result.state == "ready":
                payload = result.model_dump(mode="json")
                atomic(path, {"schemaVersion": 1, "result": payload, "digest": digest(payload)})
                return SharedProjectInsightStatus(state="ready", result=result)
            waiting = result.errorCode and ("budget" in result.errorCode or "not_configured" in result.errorCode)
            return SharedProjectInsightStatus(
                state="waiting" if waiting else "unavailable", result=result, errorCode=result.errorCode
            )
    except (ProviderWorkYield, ProviderBudgetError) as exc:
        return SharedProjectInsightStatus(state="waiting", errorCode=exc.code)
    except RardarLLMError as exc:
        return SharedProjectInsightStatus(state="unavailable", errorCode=exc.code)
    except (ValueError, OSError):
        return SharedProjectInsightStatus(state="unavailable", errorCode="project_insight_material_invalid")


async def start_project_insight(identifier: str, request: SharedProjectInsightRequest) -> SharedProjectInsightStatus:
    project = await asyncio.to_thread(_project, identifier, request)
    key = _key(project)
    task = _RUNNING.get(key)
    if task is None:

        async def run():
            try:
                status = await _execute(project, request)
                # Bounded transient failure/status cache; only valid results persist.
                if len(_LAST_STATE) >= 128:
                    _LAST_STATE.pop(next(iter(_LAST_STATE)))
                _LAST_STATE[key] = status
                return status
            finally:
                _RUNNING.pop(key, None)

        task = asyncio.create_task(run())
        _RUNNING[key] = task
    # A closing browser must not cancel an in-flight request after it is charged.
    return await asyncio.shield(task)
