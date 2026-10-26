"""Recovery decisions projected from existing material and attempt receipts.

No independent queue, retry ledger, scheduler or persisted state lives here.
The daily worker owns admission, writer locking and the shared Provider budget.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import httpx

from app.integrations.rardar.profile_cache_v2 import ProfileAttemptRecordV1, digest
from app.services.llm.provider_budget import ProviderBudgetError

_TRANSIENT_SOURCE = frozenset(
    {
        "profile_source_timeout",
        "profile_source_rate_limited",
        "profile_source_http_5xx",
        "profile_source_remote_disconnected",
        "profile_source_http_404",
    }
)
_TRANSIENT_MODEL = frozenset(
    {
        "profile_translation_unavailable",
        "profile_model_unavailable",
        "profile_build_interrupted",
        "profile_unknown_failure",
    }
)
_BUDGET_WAIT = frozenset(
    {
        "provider_daily_budget_unconfigured",
        "provider_budget_exhausted",
        "daily_budget_exhausted",
        "daily_budget_not_configured",
    }
)
_COOPERATIVE_WAIT = frozenset(
    {
        "interactive_request_waiting",
        "provider_request_busy",
        "pre_window_background_limit",
        "work_slice_exhausted",
        "calendar_day_changed",
    }
)


def source_content_digest(evidence) -> str:
    """Version reading inputs, not board dates, metric churn or binding names.

    This digest is a change signal only. It does not replace strict evidence
    hashes, numeric identity checks or the route/rule-bound cache identity.
    """
    value = evidence if isinstance(evidence, dict) else evidence.model_dump(mode="json")
    return digest(
        {
            key: value[key]
            for key in (
                "githubRepositoryId",
                "readmePath",
                "sourceLanguage",
                "selectedSections",
                "originalExcerpts",
                "topLevelTree",
                "pathRefs",
            )
        }
        | {"evidenceIndex": {key: text for key, text in value["evidenceIndex"].items() if key != "repository"}}
    )


def material_next_action(
    *,
    identity_verified: bool,
    material: dict | None = None,
    attempt: ProfileAttemptRecordV1 | None = None,
    has_saved_stages: bool = False,
    budget_available: bool | None = None,
    source_changed: bool = False,
    integrity_error: bool = False,
    missing_stages: tuple[str, ...] = (),
    previous_code: str | None = None,
    now: datetime | None = None,
) -> dict:
    """Explain the next permitted operation, not whether a new call is funded.

    Inputs must already pass the store's integrity/compatibility readers. A
    profile being nonempty is not evidence of compatible, publishable content.
    Budget ``None`` means not checked, never an assertion of zero consumption.
    """
    clock = now or datetime.now(UTC)
    code = attempt.errorCode if attempt is not None else previous_code
    retry_at = attempt.nextRetryAt if attempt is not None else None
    result = {
        "action": "resume_missing_stage",
        "reason": "missing_material_stage",
        "nextAllowedAt": retry_at.isoformat() if retry_at else None,
        "canReassemble": bool(has_saved_stages and identity_verified and not integrity_error),
        "requiresProvider": True,
        "missingStages": list(missing_stages),
    }

    def choose(action: str, reason: str, *, provider: bool = False) -> dict:
        return {**result, "action": action, "reason": reason, "requiresProvider": provider}

    if integrity_error or code == "material_integrity_invalid":
        return choose("not_recoverable_without_new_input", "material_integrity_invalid")
    if not identity_verified or code in {
        "profile_evidence_mismatch",
        "repository_identity_mismatch",
        "repository_identity_evidence_required",
    }:
        return {**choose("needs_identity_evidence", code or "repository_identity_unverified"), "canReassemble": False}
    if code == "profile_path_unsafe":
        return {**choose("not_recoverable_without_new_input", code), "canReassemble": False}
    if source_changed:
        return choose("fetch_changed_source", "material_source_changed")
    if material is not None and material.get("materialState") == "complete" and material.get("displayProfile"):
        return choose("reuse_healthy", "compatible_material_saved")
    # Already saved compatible stages can recover reading fields without a new
    # source/model call, even when the next paid retry is cooling or unfunded.
    if has_saved_stages:
        return choose("cache_only_reassemble", "compatible_stage_available")
    if code in _BUDGET_WAIT:
        return choose("defer_budget", code)
    if code in _COOPERATIVE_WAIT:
        return choose("resume_missing_stage", code)
    if code in {"profile_evidence_incomplete", "profile_source_invalid"}:
        return choose("degrade_with_evidence", code)
    if attempt is not None and not attempt.retryable:
        return choose("not_recoverable_without_new_input", code)
    if retry_at is not None and clock < retry_at:
        return choose("retry_transient_later", code or "recorded_retry_cooldown")
    if code in _TRANSIENT_SOURCE:
        return choose("fetch_changed_source", code)
    if budget_available is False:
        return choose("defer_budget", "daily_budget_unavailable")
    if code in _TRANSIENT_MODEL or code == "profile_model_invalid_output":
        return choose("resume_missing_stage", code, provider=True)
    return result


@dataclass(frozen=True)
class CachedMaterial:
    """A verified saved-source projection, not a newly fetched source claim."""

    collected: object
    project: object
    context: object
    introduction: dict
    route_identity: str
    receipt: dict


def _deny_external(_request: httpx.Request) -> httpx.Response:
    raise RuntimeError("material_reassembly_external_request_forbidden")


async def collect_cached_material(target: Path, project: dict, route_identity: str) -> CachedMaterial | None:
    """Reassemble compatible stages against one saved, validated source witness.

    Missing stage/source data returns ``None``. Integrity failures propagate so
    callers do not silently replace a damaged artifact with another paid run.
    This operation never writes, fetches sources or calls a Provider.
    """
    from app.integrations.rardar import project_identity, serving_profiles, trending_metadata
    from app.integrations.rardar.serving_schemas import ProjectEvidenceProjection
    from app.services.rardar_cache_reassembly import _source_witness

    metadata = trending_metadata.read(target, project)
    if metadata is None:
        return None
    identifier = metadata["githubRepositoryId"]
    if project.get("githubRepositoryId") not in (None, identifier):
        raise ValueError("material_reassembly_identity_mismatch")
    continuity = project_identity.resolve(target, project)
    aliases = (continuity or {}).get("aliases", [metadata["repository"]])
    witness = None
    for repository in dict.fromkeys([metadata["repository"], *aliases]):
        try:
            witness = _source_witness(target / "profile-cache", repository, identifier)
            break
        except ProviderBudgetError as exc:
            if exc.code == "provider_budget_unsafe_path":
                raise ValueError("material_reassembly_path_invalid") from exc
            raise
        except ValueError as exc:
            if str(exc) not in {"cache_reassembly_introduction_missing", "cache_reassembly_readme_missing"}:
                raise
    if witness is None:
        return None
    introduction, readme = witness
    evidence = ProjectEvidenceProjection.model_validate(introduction["evidence"], strict=True)
    revision = trending_metadata.content_revision(target, project)
    branch = (revision or {}).get("content", {}).get("defaultBranch") or project.get("defaultBranch") or "HEAD"
    facts = SimpleNamespace(
        githubRepositoryId=identifier,
        repository=evidence.repository,
        htmlUrl=f"https://github.com/{evidence.repository}",
        # HEAD is a link to the repository's default branch, not a claim that
        # an old metadata record proved that the branch was named "main".
        defaultBranch=branch,
        description=evidence.evidenceIndex.get("description"),
        primaryLanguage=metadata["language"],
        topics=metadata["topics"],
        licenseSpdxId=metadata["license"],
        pushedAt=None,
    )
    context = serving_profiles._build_evidence_context(facts, evidence.generationId, evidence.topLevelTree, readme)
    if context.evidence != evidence:
        raise ValueError("material_reassembly_source_fingerprint_mismatch")
    async with httpx.AsyncClient(transport=httpx.MockTransport(_deny_external)) as client:
        try:
            collected = await serving_profiles.collect_official_project_profile(
                facts,
                evidence.generationId,
                target / "profile-cache",
                client=client,
                translate=True,
                allow_model_generation=False,
                model_route_identity=route_identity,
                cache_only=True,
                cached_source=(evidence.topLevelTree, readme),
                save_partial_introduction=False,
            )
        except ValueError as exc:
            if str(exc) in {
                "cache_reassembly_official_translation_missing",
                "cache_reassembly_official_positioning_missing",
                "cache_reassembly_assessment_missing",
                "cache_only_profile_not_publishable",
            }:
                return None
            raise
    if collected.github_requests or collected.translation_calls:
        raise ValueError("material_reassembly_not_cache_only")
    # The collector builds a new projection, but it did not generate new model
    # text. Preserve known generation time; otherwise retain the first source
    # save time only as the schema's assembly time and explicitly report that
    # the model-generation timestamp remains unknown.
    old_partial = introduction.get("partialProfile") or {}
    generated_at = introduction["generatedAt"]
    profile_time = generated_at or old_partial.get("generatedAt") or introduction["savedAt"]
    profile = collected.profile.model_copy(update={"generatedAt": datetime.fromisoformat(profile_time)})
    collected = replace(collected, profile=profile)
    receipt = {
        "sourceMode": "saved_evidence_not_refetched",
        "sourceGeneration": evidence.generationId,
        "sourceEvidenceDigest": evidence.digest,
        "sourceEvidenceSavedAt": introduction["savedAt"],
        "modelGeneratedAt": generated_at,
        "profileTimeSource": (
            "saved_generation" if generated_at else "saved_profile_assembly" if old_partial else "first_saved_source"
        ),
        "repositoryMetadataFetchedAt": metadata["fetchedAt"],
        "readmeCheckedAt": None,
        "sourceRequests": 0,
        "providerRequests": 0,
    }
    return CachedMaterial(collected, facts, context, introduction, route_identity, receipt)


def persist_cached_material(target: Path, cached: CachedMaterial) -> object:
    """Persist/read back through existing stores while caller owns writer.lock."""
    from app.integrations.rardar import project_introductions, serving_profiles
    from app.services.rardar_trending import project_material, saved_materials

    collected = cached.collected
    profile = collected.profile
    if serving_profiles._profile_is_publishable(profile):
        profile, identity, revision, binding, remapped = serving_profiles._persist_and_bind_profile(
            target / "profile-cache",
            cached.project,
            cached.context.evidence.generationId,
            cached.context,
            profile,
            model_route_identity=cached.route_identity,
            model_derived_used=collected.translation_cache_hit,
            deterministic_fallback_used=collected.deterministic_fallback_used,
        )
        collected = replace(
            collected,
            profile=profile,
            profile_cache_identity=identity.identityDigest,
            profile_revision=revision,
            profile_binding_digest=binding,
            evidence_refs_remapped=remapped,
            profile_cache_state="rebound",
        )
    elif collected.profile_cache_state == "partial_reused":
        # This is already a durable strictly-bound partial profile. Writing it
        # into the full V2 store would collide with later complete material.
        project_material(profile, collected.evidence)
    else:
        identity = serving_profiles._profile_identity_for_result(
            cached.project,
            collected.evidence,
            profile,
            model_route_identity=cached.route_identity,
            model_derived_used=collected.translation_cache_hit,
            deterministic_fallback_used=collected.deterministic_fallback_used,
        )
        summary = profile.identitySummaryZh
        project_introductions.save(
            target / "profile-cache",
            collected.evidence,
            summary,
            profile.claimEvidenceRefs.get(summary, []),
            source_mode="official_zh" if profile.sourceLanguage == "zh" else "validated_translation",
            source_label=profile.sourceLabel,
            generated_at=cached.receipt["modelGeneratedAt"],
            partial_profile=profile,
            reuse_identity=identity,
            deterministic_fallback_used=collected.deterministic_fallback_used,
        )
    saved = saved_materials(target, repositories={profile.repository}).get(profile.repository)
    if not saved or saved.get("githubRepositoryId") != profile.githubRepositoryId or not saved.get("profile"):
        raise ValueError("material_reassembly_readback_failed")
    return collected
