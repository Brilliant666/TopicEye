"""Explicit, cache-only correction of two evidence-bound Rardar Profiles.

Preview never writes. Apply holds the daily writer lock, repeats the preview,
and persists through the existing V2 Profile store. No source or model client is
created by this module.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import httpx

from app.core.config import settings
from app.integrations.rardar import project_introductions, serving_profiles, trending_metadata
from app.integrations.rardar.profile_cache_v2 import (
    _read_plain,
    rebind_profile,
    semantic_profile_revision,
    store_profile,
)
from app.integrations.rardar.project_identity import project_id_for_repository
from app.integrations.rardar.serving_schemas import ProjectEvidenceProjection
from app.services.llm.provider_budget import atomic, digest, file_lock, plain
from app.services.rardar_daily_operations import operation_root
from app.services.rardar_llm_control import resolve_rardar_route_identity
from app.services.rardar_trending import detail, project_material, saved_materials

ALLOWED_REPOSITORIES = frozenset({"zai-org/zcode", "hydra-db/hydradb"})
REASSEMBLY_VERSION = "cache-reassembly-v1"


def _deny_external(_request: httpx.Request) -> httpx.Response:
    raise RuntimeError("cache_reassembly_external_request_forbidden")


def _source_witness(cache_root: Path, repository: str, repository_id: int) -> tuple[dict, dict]:
    directory = cache_root / "introductions" / str(repository_id)
    plain(directory, missing=True)
    introductions = []
    paths = sorted(directory.glob("*.json"))
    if len(paths) > 128:
        raise ValueError("cache_reassembly_introductions_unbounded")
    for path in paths:
        value = project_introductions.read(path)
        if value["repository"] == repository and value["githubRepositoryId"] == repository_id:
            introductions.append(value)
    if not introductions:
        raise ValueError("cache_reassembly_introduction_missing")
    introduction = max(introductions, key=lambda value: value["savedAt"])
    evidence = ProjectEvidenceProjection.model_validate(introduction["evidence"], strict=True)
    sha = evidence.readmeBlobSha
    if sha is None:
        raise ValueError("cache_reassembly_readme_missing")
    path = cache_root / "readmes" / str(repository_id) / f"{sha}.json"
    raw = _read_plain(path, root=cache_root)
    if raw is None:
        raise ValueError("cache_reassembly_readme_missing")
    readme = json.loads(raw)
    if (
        not isinstance(readme, dict)
        or readme.get("repository") != repository
        or readme.get("sha") != sha
        or readme.get("path") != evidence.readmePath
        or not isinstance(readme.get("markdown"), str)
    ):
        raise ValueError("cache_reassembly_readme_mismatch")
    return introduction, readme


def _stage_hashes(cache_root: Path, repository_id: int) -> dict[str, str]:
    result = {}
    for stage in ("official-translations", "official-positionings", "rardar-assessments"):
        directory = cache_root / stage / str(repository_id)
        plain(directory, missing=True)
        paths = sorted(directory.glob("*.json"))
        if len(paths) > 128:
            raise ValueError("cache_reassembly_stage_inventory_unbounded")
        for path in paths:
            raw = _read_plain(path, maximum=12_000_000, root=cache_root)
            if raw is None or len(raw) > 12_000_000:
                raise ValueError("cache_reassembly_stage_invalid")
            result[f"{stage}/{path.name}"] = hashlib.sha256(raw).hexdigest()
    return result


async def preview(repository: str) -> tuple[dict, object, object, object]:
    if repository not in ALLOWED_REPOSITORIES:
        raise ValueError("cache_reassembly_repository_not_allowed")
    if not settings.RARDAR_INTELLIGENCE_DATA_DIR:
        raise ValueError("cache_reassembly_data_unconfigured")
    target = Path(settings.RARDAR_INTELLIGENCE_DATA_DIR)
    project_id = project_id_for_repository(repository)
    fact = detail(project_id, None, historical=True)
    if fact["repository"] != repository or fact["projectId"] != project_id:
        raise ValueError("cache_reassembly_fact_identity_mismatch")
    metadata = trending_metadata.read(target, fact)
    if metadata is None or metadata["githubRepositoryId"] != fact.get("githubRepositoryId"):
        raise ValueError("cache_reassembly_metadata_mismatch")
    cache_root = target / "profile-cache"
    introduction, readme = _source_witness(cache_root, repository, metadata["githubRepositoryId"])
    saved_evidence = ProjectEvidenceProjection.model_validate(introduction["evidence"], strict=True)
    project = SimpleNamespace(
        githubRepositoryId=metadata["githubRepositoryId"],
        repository=repository,
        htmlUrl=f"https://github.com/{repository}",
        description=saved_evidence.evidenceIndex.get("description"),
        defaultBranch="main",  # DTO default; no new upstream identity claim.
        primaryLanguage=metadata["language"],
        topics=metadata["topics"],
        licenseSpdxId=metadata["license"],
        pushedAt=None,
    )
    context = serving_profiles._build_evidence_context(
        project, saved_evidence.generationId, saved_evidence.topLevelTree, readme
    )
    if context.evidence != saved_evidence:
        raise ValueError("cache_reassembly_source_fingerprint_mismatch")
    route = await resolve_rardar_route_identity()
    existing = saved_materials(target, repositories={repository}).get(repository)
    if existing and existing.get("displayProfile") is not None and existing.get("materialState") == "complete":
        return (
            {"state": "reused", "repository": repository, "projectId": project_id, "externalRequests": 0},
            None,
            None,
            None,
        )
    async with httpx.AsyncClient(transport=httpx.MockTransport(_deny_external)) as client:
        collected = await serving_profiles.collect_official_project_profile(
            project,
            saved_evidence.generationId,
            cache_root,
            client=client,
            translate=True,
            allow_model_generation=False,
            model_route_identity=route,
            cache_only=True,
            cached_source=(saved_evidence.topLevelTree, readme),
            save_partial_introduction=False,
        )
    if (
        collected.github_requests
        or collected.translation_calls
        or not collected.translation_cache_hit
        or not serving_profiles._profile_is_publishable(collected.profile)
    ):
        raise ValueError("cache_reassembly_not_cache_only_publishable")
    projected = project_material(collected.profile, collected.evidence)
    if projected["materialState"] != "complete":
        raise ValueError("cache_reassembly_material_incomplete")
    plan = {
        "version": REASSEMBLY_VERSION,
        "repository": repository,
        "projectId": project_id,
        "repositoryId": metadata["githubRepositoryId"],
        "sourceGeneration": saved_evidence.generationId,
        "evidenceDigest": saved_evidence.digest,
        "sourceGeneratedAt": introduction["generatedAt"],
        "sourceSavedAt": introduction["savedAt"],
        "readmeSha": saved_evidence.readmeBlobSha,
        "routeIdentity": route,
        "ruleVersions": serving_profiles._profile_identity_versions(),
        "stageHashes": _stage_hashes(cache_root, metadata["githubRepositoryId"]),
        "existingMaterialDigest": digest(existing),
        "profileRevision": semantic_profile_revision(collected.profile),
        "positioning": collected.profile.positioningZh,
        "positioningEvidenceRefs": collected.profile.positioningEvidenceRefs,
        "qualityState": collected.profile.qualityState,
        "profileState": collected.profile.profileState,
        "materialState": projected["materialState"],
        "writeScope": ["profile-cache/profile-store/v2", "daily-operations/cache-reassembly"],
        "externalRequests": 0,
    }
    plan["planDigest"] = digest(plan)
    return plan, project, collected, context


async def apply(repository: str, expected_plan_digest: str) -> dict:
    if len(expected_plan_digest) != 64 or any(char not in "0123456789abcdef" for char in expected_plan_digest):
        raise ValueError("cache_reassembly_plan_digest_invalid")
    root = operation_root()
    root.mkdir(parents=True, exist_ok=True)
    with file_lock(root / "writer.lock", blocking=False):
        plan, project, collected, context = await preview(repository)
        if plan.get("state") == "reused":
            return plan
        if plan["planDigest"] != expected_plan_digest:
            raise ValueError("cache_reassembly_plan_stale")
        target = Path(settings.RARDAR_INTELLIGENCE_DATA_DIR)
        cache_root = target / "profile-cache"
        identity = serving_profiles._profile_identity_for_result(
            project,
            collected.evidence,
            collected.profile,
            model_route_identity=plan["routeIdentity"],
            model_derived_used=collected.translation_cache_hit,
            deterministic_fallback_used=collected.deterministic_fallback_used,
        )
        envelope = store_profile(
            cache_root,
            identity,
            collected.profile,
            collected.evidence,
            deterministic_fallback_used=collected.deterministic_fallback_used,
        )
        rebound, binding, _ = rebind_profile(
            envelope,
            identity,
            context.evidence,
            project,
            context.evidence.generationId,
            start_here=serving_profiles._start_here(
                project, context.readme_path, context.sections, context.tree, context.path_refs
            ),
        )
        project_material(rebound, context.evidence)
        saved = saved_materials(target, repositories={repository}).get(repository)
        if not saved or saved.get("materialState") != "complete" or not saved.get("displayProfile"):
            raise ValueError("cache_reassembly_readback_failed")
        receipt = {
            "version": REASSEMBLY_VERSION,
            "repository": repository,
            "projectId": plan["projectId"],
            "planDigest": expected_plan_digest,
            "profileRevision": envelope.profileRevision,
            "profileIdentity": identity.identityDigest,
            "profileBindingDigest": binding.bindingDigest,
            "sourceGeneration": context.evidence.generationId,
            "sourceEvidenceDigest": context.evidence.digest,
            "sourceGeneratedAt": plan["sourceGeneratedAt"],
            "sourceSavedAt": plan["sourceSavedAt"],
            "reassembledAt": datetime.now(UTC).isoformat(),
            "stageGeneratedAt": None,
            "materialState": saved["materialState"],
            "externalRequests": 0,
        }
        path = root / "cache-reassembly" / f"{plan['projectId']}.json"
        plain(path, missing=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic(path, receipt)
        return receipt
