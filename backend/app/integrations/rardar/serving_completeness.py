"""Fail-closed publication completeness audit for Rardar's exact Today Top 20."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from app.integrations.rardar.serving_profiles import (
    ProfileBuildResult,
    _primary_semantic_duplicate,
    _publishable_primary_text,
    _text_issue_codes,
)
from app.integrations.rardar.serving_schemas import ServingCapability, ServingTodaySnapshot, TodayProject

_GENERIC_CAPABILITY_TITLE = re.compile(
    r"^(?:能力|功能|特性|插件|工具|主要能力|核心能力|功能特性|能力说明\s*\d+|功能说明\s*\d+)$",
    re.IGNORECASE,
)
_OPERATION_OR_DEPLOYMENT = re.compile(
    r"(?:\b(?:install|installation|quickstart|quick\s+start|deploy|deployment|benchmark|"
    r"test suite|run\s+(?:npm|pnpm|yarn|pip|docker)|single.{0,16}(?:rust\s*)?binary)\b|"
    r"安装|快速开始|部署|运行命令|测试方法|基准测试|单个.{0,16}(?:rust\s*)?二进制|没有\s*electron)",
    re.IGNORECASE,
)


def _capability_audit(
    capabilities: list[ServingCapability],
    allowed_refs: set[str] | None,
) -> dict[str, int]:
    counts = Counter()
    identities: Counter[tuple[str, str]] = Counter()
    for capability in capabilities:
        issues = {
            *_text_issue_codes(capability.title, capability=True),
            *_text_issue_codes(capability.detail, capability=True),
        }
        if _GENERIC_CAPABILITY_TITLE.fullmatch(capability.title.strip()):
            counts["generic"] += 1
        if "placeholder_capability" in issues:
            counts["placeholder"] += 1
        if "long_english" in issues or not re.search(r"[\u3400-\u9fff]", capability.detail):
            counts["untranslated"] += 1
        if "navigation_noise" in issues:
            counts["navigation"] += 1
        if {"image_or_badge_noise", "html_noise"}.intersection(issues):
            counts["html_image"] += 1
        if "url_only" in issues:
            counts["pure_url"] += 1
        if _OPERATION_OR_DEPLOYMENT.search(f"{capability.title} {capability.detail}"):
            counts["operation"] += 1
        if (
            not capability.evidenceRefs
            or allowed_refs is not None
            and not set(capability.evidenceRefs).issubset(allowed_refs)
        ):
            counts["missing_evidence"] += 1
        if capability.sourceMode is None:
            counts["missing_source"] += 1
        identity = (
            re.sub(r"[^0-9a-z\u3400-\u9fff]+", "", capability.title.casefold()),
            re.sub(r"[^0-9a-z\u3400-\u9fff]+", "", capability.detail.casefold()),
        )
        identities[identity] += 1
    counts["duplicate"] = sum(value - 1 for value in identities.values() if value > 1)
    return dict(counts)


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
    detail_capabilities: list[list[ServingCapability]] = []
    capability_audits: list[dict[str, int]] = []
    for project in projects:
        collected = profiles.profiles.get(project.githubRepositoryId) if profiles is not None else None
        capabilities = list(collected.profile.capabilities) if collected is not None else list(project.capabilities)
        allowed_refs = set(collected.evidence.evidenceIndex) if collected is not None else None
        detail_capabilities.append(capabilities)
        capability_audits.append(_capability_audit(capabilities, allowed_refs))
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
                "capabilityCount": len(detail_capabilities[len(profile_diagnostics)]),
                "capabilitySourceModes": dict(
                    Counter(item.sourceMode for item in detail_capabilities[len(profile_diagnostics)])
                ),
                "capabilityIssues": capability_audits[len(profile_diagnostics)],
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
    capability_non_empty = sum(bool(capabilities) for capabilities in detail_capabilities)
    capability_item_total = sum(len(capabilities) for capabilities in detail_capabilities)
    capability_modes = Counter(
        capability.sourceMode for capabilities in detail_capabilities for capability in capabilities
    )
    single_capability_projects = sum(len(capabilities) == 1 for capabilities in detail_capabilities)
    capability_issue_totals = Counter(
        {
            key: sum(audit.get(key, 0) for audit in capability_audits)
            for key in {
                "placeholder",
                "generic",
                "untranslated",
                "navigation",
                "html_image",
                "pure_url",
                "operation",
                "duplicate",
                "missing_evidence",
                "missing_source",
            }
        }
    )
    activation_allowed = bool(
        not strict_top20
        or (
            total == 20
            and identity_complete == 20
            and positioning_complete == 20
            and capability_non_empty == 20
            and insufficient_count == 0
            and rejected_count == 0
            and not unresolved
            and placeholder_count == 0
            and navigation_count == 0
            and pure_url_count == 0
            and html_image_count == 0
            and untranslated_count == 0
            and not any(capability_issue_totals.values())
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
        "detailProjectionReadyCount": capability_non_empty,
        "capabilitySectionVisibleCount": capability_non_empty,
        "capabilityNonEmptyCount": capability_non_empty,
        "capabilityItemTotal": capability_item_total,
        "capabilityOfficialZhCount": capability_modes["official_zh"],
        "capabilityOfficialTranslatedCount": capability_modes["official_translated"],
        "capabilityRardarDerivedCount": capability_modes["rardar_derived"],
        "capabilityDeterministicFallbackCount": capability_modes["deterministic_fallback"],
        "singleCapabilityProjectCount": single_capability_projects,
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
        "capabilityPlaceholderCount": capability_issue_totals["placeholder"],
        "genericCapabilityTitleCount": capability_issue_totals["generic"],
        "untranslatedCapabilityCount": capability_issue_totals["untranslated"],
        "capabilityNavigationNoiseCount": capability_issue_totals["navigation"],
        "capabilityHtmlImageNoiseCount": capability_issue_totals["html_image"],
        "capabilityPureUrlCount": capability_issue_totals["pure_url"],
        "operationDeploymentLeakageCount": capability_issue_totals["operation"],
        "duplicateCapabilityCount": capability_issue_totals["duplicate"],
        "missingCapabilityEvidenceCount": capability_issue_totals["missing_evidence"],
        "missingCapabilitySourceCount": capability_issue_totals["missing_source"],
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
