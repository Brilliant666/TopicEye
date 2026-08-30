"""Fail-closed publication completeness audit for Rardar's exact Today Top 20."""

from __future__ import annotations

from collections import Counter
from typing import Any

from app.integrations.rardar.serving_profiles import (
    ProfileBuildResult,
    _primary_semantic_duplicate,
    _publishable_primary_text,
    _text_issue_codes,
)
from app.integrations.rardar.serving_schemas import ServingTodaySnapshot, TodayProject


def _project_issues(project: TodayProject) -> set[str]:
    values = [project.identitySummaryZh or "", project.positioningZh or ""]
    return {issue for value in values for issue in _text_issue_codes(value)}


def _identity_complete(project: TodayProject) -> bool:
    return bool(project.qualityState != "rejected" and _publishable_primary_text(project.identitySummaryZh))


def _positioning_complete(project: TodayProject) -> bool:
    return bool(
        project.qualityState != "rejected"
        and project.positioningSourceMode != "insufficient"
        and _publishable_primary_text(project.positioningZh)
        and project.positioningEvidenceRefs
        and project.positioningIncludedRoles
        and bool({"core_mechanism", "primary_outcome"}.intersection(project.positioningIncludedRoles))
        and not _primary_semantic_duplicate(project.identitySummaryZh or "", project.positioningZh or "")
    )


def audit_candidate_publication(
    today: ServingTodaySnapshot,
    profiles: ProfileBuildResult | None,
    *,
    candidate_serving_id: str,
) -> dict[str, Any]:
    """Return one machine-readable audit used by both diagnostics and activation."""

    projects = list(today.exactRanked[:20])
    modes = Counter(project.officialNarrativeMode for project in projects)
    positioning_modes = Counter(project.positioningSourceMode for project in projects)
    issue_sets = [_project_issues(project) for project in projects]
    failures = (
        [failure for collected in profiles.profiles.values() for failure in collected.generation_failures]
        if profiles is not None
        else []
    )
    translation_failures = [failure for failure in failures if failure.stage == "translation"]
    positioning_failures = [failure for failure in failures if failure.stage == "positioning"]
    unresolved = [failure for failure in failures if not failure.resolved]
    profile_diagnostics = []
    for project in projects:
        collected = profiles.profiles.get(project.githubRepositoryId) if profiles is not None else None
        project_failures = list(collected.generation_failures) if collected is not None else []
        profile_diagnostics.append(
            {
                "rank": project.rank,
                "githubRepositoryId": project.githubRepositoryId,
                "repository": project.repository,
                "failureCodes": [failure.code for failure in project_failures],
                "unresolvedFailureCodes": [failure.code for failure in project_failures if not failure.resolved],
                "deterministicFallbackUsed": bool(collected is not None and collected.deterministic_fallback_used),
                "lastKnownGoodAvailable": bool(collected is not None and collected.last_known_good_available),
                "lastKnownGoodReused": bool(collected is not None and collected.last_known_good_reused),
                "currentEvidenceFingerprint": (
                    collected.current_evidence_fingerprint if collected is not None else None
                ),
                "lastKnownGoodFingerprint": (collected.last_known_good_fingerprint if collected is not None else None),
            }
        )
    total = len(projects)
    coverage_count = today.coverage.exactCount if today.coverage is not None else 0
    strict_top20 = total >= 20 or coverage_count >= 20
    identity_complete = sum(_identity_complete(project) for project in projects)
    positioning_complete = sum(_positioning_complete(project) for project in projects)
    placeholder_count = sum("placeholder_text" in issues for issues in issue_sets)
    navigation_count = sum("navigation_noise" in issues for issues in issue_sets)
    pure_url_count = sum("url_only" in issues for issues in issue_sets)
    html_image_count = sum(bool({"image_or_badge_noise", "html_noise"}.intersection(issues)) for issues in issue_sets)
    untranslated_count = sum("long_english" in issues for issues in issue_sets)
    rejected_count = sum(project.qualityState == "rejected" for project in projects)
    insufficient_count = positioning_modes["insufficient"]
    activation_allowed = bool(
        not strict_top20
        or (
            total == 20
            and identity_complete == 20
            and positioning_complete == 20
            and insufficient_count == 0
            and rejected_count == 0
            and not unresolved
            and placeholder_count == 0
            and navigation_count == 0
            and pure_url_count == 0
            and html_image_count == 0
            and untranslated_count == 0
        )
    )
    return {
        "schemaVersion": 1,
        "candidateServingId": candidate_serving_id,
        "sourceGenerationId": today.generationId,
        "top20GateRequired": strict_top20,
        "top20Total": total,
        "identityCompleteCount": identity_complete,
        "positioningCompleteCount": positioning_complete,
        "officialZhCount": modes["official_zh"],
        "officialTranslatedCount": modes["official_translated"],
        "rardarDerivedCount": modes["rardar_derived"],
        "deterministicFallbackCount": sum(
            collected.deterministic_fallback_used for collected in profiles.profiles.values()
        )
        if profiles is not None
        else 0,
        "lastKnownGoodReuseCount": sum(collected.last_known_good_reused for collected in profiles.profiles.values())
        if profiles is not None
        else 0,
        "insufficientCount": insufficient_count,
        "translationFailureCount": len(translation_failures),
        "positioningFailureCount": len(positioning_failures),
        "unresolvedFailureCount": len(unresolved),
        "failureCodes": dict(Counter(failure.code for failure in failures)),
        "unresolvedFailureCodes": dict(Counter(failure.code for failure in unresolved)),
        "profileDiagnostics": profile_diagnostics,
        "placeholderCount": placeholder_count,
        "navigationNoiseCount": navigation_count,
        "pureUrlCount": pure_url_count,
        "htmlImageNoiseCount": html_image_count,
        "longUntranslatedCount": untranslated_count,
        "rejectedRenderedCount": rejected_count,
        "activationAllowed": activation_allowed,
        "activationPerformed": False,
        "previousServingId": None,
        "finalServingId": None,
    }
