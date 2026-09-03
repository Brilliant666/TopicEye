"""Read-only profile qualification and deterministic local review cohort freeze."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.integrations.rardar.adapter import _SafeRoot
from app.integrations.rardar.profile_cache_v2 import ProfileAttemptRecordV1, ProfileStoreEnvelopeV2, rebind_profile
from app.integrations.rardar.selection import (
    _SUBSTANTIVE_CHANGE,
    _category,
    _contract_versions,
    _profile_project,
    _source_identities,
    _value_evidence,
    build_candidate_universe,
    negative_control_cases,
    recall_candidates,
)
from app.integrations.rardar.selection_schemas import SelectionCandidateFacts, SelectionEvidenceAlias
from app.integrations.rardar.selection_source import LoadedSelectionSource, SelectionSourceAdapter
from app.integrations.rardar.serving_profiles import (
    CollectedProjectProfile,
    _profile_identity_for_result,
    _profile_is_publishable,
)
from app.services.llm.provider_budget import atomic, digest, plain

COHORT_VERSION = "shadow-review-cohort-v1"


class ShadowIntegrityError(ValueError):
    pass


@dataclass(frozen=True)
class HealthyProfile:
    candidate: SelectionCandidateFacts
    collected: CollectedProjectProfile
    relative_path: str
    file_digest: str
    category: str
    releases: tuple[SelectionEvidenceAlias, ...]


def _read(root: Path, relative: str) -> bytes:
    return _SafeRoot(str(root)).read_stable(relative, maximum_bytes=4 * 1024 * 1024)


def healthy_pool(mirror: Path) -> tuple[LoadedSelectionSource, list[SelectionCandidateFacts], list[HealthyProfile]]:
    """Never generates, migrates, fetches, updates attempts or writes cache files."""
    source = SelectionSourceAdapter.from_config(str(mirror)).load()
    universe, _summary = build_candidate_universe(source)
    recalled = recall_candidates(universe)
    pool: list[HealthyProfile] = []
    for index, candidate in enumerate(recalled, 1):
        directory = mirror / "selection-profile-cache" / "profile-store" / "v2" / str(candidate.githubRepositoryId)
        plain(directory, missing=True)
        matches: list[tuple[str, bytes, ProfileStoreEnvelopeV2, CollectedProjectProfile]] = []
        for path in sorted(directory.glob("*.json")):
            relative = path.relative_to(mirror).as_posix()
            raw = _read(mirror, relative)
            envelope = ProfileStoreEnvelopeV2.model_validate_json(raw, strict=True)
            if envelope.cacheIdentity.repositoryId != candidate.githubRepositoryId:
                raise ShadowIntegrityError("shadow_profile_identity_mismatch")
            project = _profile_project(candidate, index)
            identity = _profile_identity_for_result(
                project,
                envelope.evidence,
                envelope.profile,
                model_route_identity=envelope.cacheIdentity.modelRouteIdentity,
                model_derived_used=not envelope.deterministicFallbackUsed,
                deterministic_fallback_used=envelope.deterministicFallbackUsed,
            )
            if identity != envelope.cacheIdentity:
                continue  # Healthy historical revision is not this source's profile.
            profile, binding, refs = rebind_profile(
                envelope,
                identity,
                envelope.evidence,
                project,
                source.source_observation_set_id,
                start_here=envelope.profile.startHere,
            )
            if not _profile_is_publishable(profile):
                continue
            collected = CollectedProjectProfile(
                profile=profile,
                evidence=envelope.evidence,
                github_requests=0,
                readme_cache_hit=True,
                translation_calls=0,
                translation_cache_hit=True,
                profile_cache_identity=identity.identityDigest,
                profile_revision=envelope.profileRevision,
                profile_binding_digest=binding.bindingDigest,
                profile_cache_state="hit",
                evidence_refs_examined=refs,
                evidence_refs_remapped=refs,
                deterministic_fallback_used=envelope.deterministicFallbackUsed,
            )
            _value_evidence(candidate, collected)  # Enforces the accepted dynamic-fact exclusion.
            matches.append((relative, raw, envelope, collected))
        if not matches:
            continue
        if len({item[2].profileRevision for item in matches}) != 1:
            raise ShadowIntegrityError("shadow_profile_revision_ambiguous")
        relative, raw, _envelope, collected = matches[0]
        releases: list[SelectionEvidenceAlias] = []
        release_path = f"selection-profile-cache/selection-releases/{candidate.githubRepositoryId}.json"
        if (mirror / release_path).exists():
            cached = json.loads(_read(mirror, release_path))
            if cached.get("sourceRevision") == candidate.pushedAt.isoformat():
                releases = [SelectionEvidenceAlias.model_validate(item, strict=True) for item in cached["evidence"]]
                if any(item.githubRepositoryId != candidate.githubRepositoryId for item in releases):
                    raise ShadowIntegrityError("shadow_release_cross_repository")
        import hashlib

        pool.append(
            HealthyProfile(
                candidate,
                collected,
                relative,
                hashlib.sha256(raw).hexdigest(),
                _category(candidate, collected),
                tuple(releases),
            )
        )
    return source, recalled, sorted(pool, key=lambda row: row.candidate.githubRepositoryId)


def choose_cohort(pool: list[HealthyProfile]) -> tuple[list[dict[str, Any]], list[str]]:
    if len(pool) < 16:
        raise ShadowIntegrityError("shadow_cohort_insufficient_profiles")
    momentum_order = sorted(
        pool, key=lambda row: (-(row.candidate.observedStarDelta or 0), row.candidate.githubRepositoryId)
    )
    high_ids = {row.candidate.githubRepositoryId for row in momentum_order[: math.ceil(len(pool) / 4)]}
    median_delta = sorted(row.candidate.observedStarDelta or 0 for row in pool)[len(pool) // 2]
    rows: list[dict[str, Any]] = []
    for row in pool:
        candidate = row.candidate
        change = bool(row.releases and _SUBSTANTIVE_CHANGE.search(" ".join(item.excerpt for item in row.releases)))
        new = candidate.lastObservedAt - candidate.createdAt <= timedelta(days=60)
        rows.append(
            {
                "githubRepositoryId": candidate.githubRepositoryId,
                "repository": candidate.repository,
                "recallChannels": candidate.recallChannels,
                "category": row.category,
                "productForms": row.collected.profile.productFormsZh,
                "momentumBand": "top_quartile" if candidate.githubRepositoryId in high_ids else "lower",
                "momentumOnly": candidate.recallChannels == ["momentum"],
                "newOrChange": new or change,
                "meaningfulChangeCandidate": change,
                "matureLowMomentum": not new and (candidate.observedStarDelta or 0) <= median_delta,
                "nonMomentumValue": bool(
                    set(candidate.recallChannels) & {"reusable_asset", "specific_problem", "reference_learning"}
                ),
                "profileRevision": row.collected.profile_revision,
                "profileEvidenceDigest": row.collected.profile.evidenceDigest,
                "profilePath": row.relative_path,
                "profileFileSha256": row.file_digest,
                "releaseEvidenceDigest": digest([item.model_dump(mode="json") for item in row.releases]),
            }
        )
    selected: list[dict[str, Any]] = []
    limitations: list[str] = []
    # Scarce strata first; never consult labels, AI output, or an aggregate Star score.
    for stratum, count, field in (
        ("new_or_change", 3, "newOrChange"),
        ("mature_low_momentum", 3, "matureLowMomentum"),
        ("high_momentum", 4, "momentumBand"),
        ("non_momentum_value", 6, "nonMomentumValue"),
    ):
        for _ in range(count):
            remaining = [
                row
                for row in rows
                if row["githubRepositoryId"] not in {item["githubRepositoryId"] for item in selected}
            ]

            def admissible(row):
                return (
                    sum(item["momentumBand"] == "top_quartile" for item in selected)
                    + (row["momentumBand"] == "top_quartile")
                    <= 6
                    and sum(item["momentumOnly"] for item in selected) + row["momentumOnly"] <= 4
                    and sum(item["meaningfulChangeCandidate"] for item in selected) + row["meaningfulChangeCandidate"]
                    <= 6
                )

            options = [
                row
                for row in remaining
                if admissible(row) and (row[field] == "top_quartile" if field == "momentumBand" else row[field])
            ]
            if not options:
                limitations.append(f"{stratum}: insufficient qualified distinct profiles; maximum attainable coverage")
                options = [row for row in remaining if admissible(row)]
            if not options:
                raise ShadowIntegrityError("shadow_cohort_constraints_unsatisfied")
            categories = {row["category"] for row in selected}
            forms = {form for row in selected for form in row["productForms"]}
            options.sort(
                key=lambda row: (
                    -(row["category"] not in categories),
                    -len(set(row["productForms"]) - forms),
                    row["githubRepositoryId"],
                )
            )
            selected.append({**options[0], "selectionStratum": stratum})
    return selected, sorted(set(limitations))


def _immutable(path: Path, payload: dict[str, Any]) -> None:
    plain(path, missing=True)
    if path.exists():
        if json.loads(path.read_bytes()) != payload:
            raise ShadowIntegrityError("shadow_freeze_conflict")
        return
    atomic(path, payload)


def freeze(mirror: Path, target: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    source, recalled, pool = healthy_pool(mirror)
    universe, _ = build_candidate_universe(source)
    identities = _source_identities(source, universe)
    selected, limitations = choose_cohort(pool)
    healthy_ids = {row.candidate.githubRepositoryId for row in pool}
    unresolved = [
        {"githubRepositoryId": row.githubRepositoryId, "repository": row.repository}
        for row in recalled
        if row.githubRepositoryId not in healthy_ids
    ]
    for row in unresolved:
        directory = mirror / "selection-profile-cache" / "profile-attempts" / "v1" / str(row["githubRepositoryId"])
        plain(directory, missing=True)
        attempts = []
        for path in directory.glob("*/*.json"):
            attempt = ProfileAttemptRecordV1.model_validate_json(
                _read(mirror, path.relative_to(mirror).as_posix()), strict=True
            )
            if attempt.repositoryId != row["githubRepositoryId"]:
                raise ShadowIntegrityError("shadow_attempt_identity_mismatch")
            attempts.append(attempt)
        if not attempts:
            raise ShadowIntegrityError("shadow_unresolved_history_missing")
        latest = max(attempts, key=lambda attempt: (attempt.lastAttemptAt, attempt.attemptId))
        row.update(
            {
                "errorCode": latest.errorCode,
                "retryable": latest.retryable,
                "attemptCount": latest.attemptCount,
                "lastAttemptAt": latest.lastAttemptAt.isoformat(),
                "nextRetryAt": latest.nextRetryAt.isoformat() if latest.nextRetryAt else None,
                "evidenceDigest": latest.profileEvidenceDigest,
            }
        )
    inventory = [
        {"path": row.relative_path, "sha256": row.file_digest, "profileRevision": row.collected.profile_revision}
        for row in pool
    ]
    source_data = {
        "schemaVersion": 1,
        "sourceObservation": source.source_observation_set_id,
        "sourceCaptureDigests": identities["sourceCaptureDigests"],
        "sourceTodayGeneration": source.today_generation_id,
        "todayTop20Digest": source.today_published_set_digest,
        "recallSetDigest": digest([row.model_dump(mode="json") for row in recalled]),
        "healthyProfileSetDigest": digest(inventory),
        "unresolvedSetDigest": digest(unresolved),
        "fullCandidateUniverseCount": len(universe),
        "fullRecallCount": len(recalled),
        "healthyProfileCount": len(pool),
        "negativeControlsDigest": digest(negative_control_cases()),
        "unresolvedProfiles": unresolved,
        "profileInventory": inventory,
    }
    plain(target, missing=True)
    target.mkdir(parents=True, exist_ok=True)
    source_path = target / "shadow-source-freeze-manifest.json"
    plain(source_path, missing=True)
    if source_path.exists():
        old = json.loads(source_path.read_bytes())
        created_at = old["createdAt"]
    else:
        created_at = datetime.now(UTC).isoformat()
    source_data["createdAt"] = created_at
    source_data["digest"] = digest(source_data)
    cohort = {
        "schemaVersion": 1,
        "cohortVersion": COHORT_VERSION,
        "sourceFreezeDigest": source_data["digest"],
        "selectionPolicyVersion": _contract_versions(),
        "items": selected,
        "limitations": limitations,
        "createdAt": created_at,
    }
    cohort["digest"] = digest(cohort)
    _immutable(source_path, source_data)
    _immutable(target / "shadow-review-cohort-manifest.json", cohort)
    return source_data, cohort
