"""Read-only semantic audit for one validated Rardar Serving Top 20."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

from app.integrations.rardar.serving import ServingProjectionLoader
from app.integrations.rardar.serving_schemas import ServingCapability, ServingProjectDetail

_CHINESE = re.compile(r"[\u3400-\u9fff]")
_PURE_URL = re.compile(r"^\s*(?:https?://|www\.)\S+\s*$", re.IGNORECASE)
_MEDIA_OR_HTML = re.compile(
    r"(?:user-attachments/assets|raw\.githubusercontent\.com|shields\.io|"
    r"<\s*(?:img|picture|source)\b|!\[[^]]*]\(|(?:^|\s)(?:src|height|width)\s*=)",
    re.IGNORECASE,
)
_REDIRECT = re.compile(
    r"(?:旧链接|兼容入口|(?:readme|documentation|文档).{0,24}(?:迁移|移至|移动|现在位于|moved|redirect)|"
    r"(?:moved|redirect).{0,40}(?:readme|documentation))",
    re.IGNORECASE,
)
_PLACEHOLDER = re.compile(r"^(?:能力说明|功能说明|capabilit(?:y|ies))\s*\d+\s*$", re.IGNORECASE)


def _normalized(value: str) -> str:
    return re.sub(r"[^0-9a-z\u3400-\u9fff]+", "", value.casefold())


def _semantic_duplicate(left: str, right: str) -> bool:
    first, second = _normalized(left), _normalized(right)
    return bool(
        first
        and second
        and (first == second or (min(len(first), len(second)) >= 12 and (first in second or second in first)))
    )


def _clear_chinese(value: str, quality_issues: list[str]) -> bool:
    return (
        len(_CHINESE.findall(value)) >= 6 and "翻译待补全" not in value and "identity_not_chinese" not in quality_issues
    )


def _capability_issues(capability: ServingCapability, allowed_refs: set[str]) -> list[str]:
    issues: list[str] = []
    if _PLACEHOLDER.fullmatch(capability.title.strip()):
        issues.append("placeholder_capability")
    title = _normalized(capability.title)
    detail = _normalized(capability.detail)
    if title == detail or (title and detail.startswith(title)):
        issues.append("title_body_duplicate")
    if not capability.evidenceRefs or not set(capability.evidenceRefs).issubset(allowed_refs):
        issues.append("invalid_evidence_ref")
    return issues


def _audit_project(detail: ServingProjectDetail) -> dict[str, Any]:
    project = detail.project
    profile = detail.profile
    identity = profile.identitySummaryZh
    allowed_refs = set(detail.evidence.evidenceIndex)
    reasons: list[str] = []
    if _PURE_URL.fullmatch(identity):
        reasons.append("url_summary")
    if _MEDIA_OR_HTML.search(identity):
        reasons.append("image_or_html_summary")
    if _REDIRECT.search(identity):
        reasons.append("redirect_summary")
    if not _clear_chinese(identity, profile.qualityIssues):
        reasons.append("non_chinese_identity")
    if len(identity) > 180 and len(re.findall(r"[A-Za-z]", identity)) > len(_CHINESE.findall(identity)) * 8:
        reasons.append("long_english_summary")
    if profile.coreValueZh is None:
        reasons.append("empty_core_value")
    elif not profile.coreValueEvidenceRefs or not set(profile.coreValueEvidenceRefs).issubset(allowed_refs):
        reasons.append("core_value_without_evidence")
    else:
        if _semantic_duplicate(profile.coreValueZh, identity):
            reasons.append("core_value_duplicates_identity")
        if any(_semantic_duplicate(profile.coreValueZh, capability.detail) for capability in profile.capabilities):
            reasons.append("core_value_duplicates_capability")
    for capability in [*profile.keyDifferentiators, *profile.capabilities]:
        reasons.extend(_capability_issues(capability, allowed_refs))
    reasons = list(dict.fromkeys(reasons))
    return {
        "rank": project.rank,
        "repository": profile.repository,
        "profileState": profile.profileState,
        "qualityState": profile.qualityState,
        "qualityIssues": profile.qualityIssues,
        "summarySource": profile.sourceLabel,
        "summaryLanguage": profile.sourceLanguage,
        "identitySummaryZh": identity,
        "coreValueZh": profile.coreValueZh,
        "capabilityCount": len(profile.capabilities),
        "invalidContentReasons": reasons,
        "translationState": profile.translationState,
        "recommendedRepairPath": "none" if not reasons else "rebuild_from_sanitized_official_evidence",
    }


def audit_serving_top20(target: Path) -> dict[str, Any]:
    """Audit the current immutable Serving generation without network or model calls."""

    loader = ServingProjectionLoader(target)
    today, _etag = loader.load_today_with_etag()
    entries: list[dict[str, Any]] = []
    for project in today.exactRanked[:20]:
        detail, _etag = loader.load_project_with_etag(project.githubRepositoryId, today.generationId)
        entries.append(_audit_project(detail))

    quality = Counter(entry["qualityState"] for entry in entries)
    invalid = Counter(reason for entry in entries for reason in entry["invalidContentReasons"])
    top_ten = entries[:10]
    summary = {
        "total": len(entries),
        "ready": quality["ready"],
        "partial": quality["partial"],
        "rejected": quality["rejected"],
        "chineseIdentitySummaries": sum(
            "non_chinese_identity" not in entry["invalidContentReasons"] for entry in entries
        ),
        "chineseCoreValues": sum(
            entry["coreValueZh"] is not None and len(_CHINESE.findall(entry["coreValueZh"])) >= 6 for entry in entries
        ),
        "top10ChineseIdentitySummaries": sum(
            "non_chinese_identity" not in entry["invalidContentReasons"] for entry in top_ten
        ),
        "top10ChineseCoreValues": sum(
            entry["coreValueZh"] is not None and len(_CHINESE.findall(entry["coreValueZh"])) >= 6 for entry in top_ten
        ),
        "urlSummaries": invalid["url_summary"],
        "imageOrHtmlSummaries": invalid["image_or_html_summary"],
        "redirectSummaries": invalid["redirect_summary"],
        "longEnglishSummaries": invalid["long_english_summary"],
        "placeholderCapabilities": invalid["placeholder_capability"],
        "emptyCoreValues": invalid["empty_core_value"],
        "coreValuesWithoutEvidence": invalid["core_value_without_evidence"],
        "coreValueDuplicates": invalid["core_value_duplicates_identity"] + invalid["core_value_duplicates_capability"],
        "titleBodyDuplicates": invalid["title_body_duplicate"],
        "invalidEvidenceRefs": invalid["invalid_evidence_ref"],
    }
    zero_fields = (
        "urlSummaries",
        "imageOrHtmlSummaries",
        "redirectSummaries",
        "longEnglishSummaries",
        "placeholderCapabilities",
        "emptyCoreValues",
        "coreValuesWithoutEvidence",
        "coreValueDuplicates",
        "titleBodyDuplicates",
        "invalidEvidenceRefs",
    )
    passed = (
        summary["total"] == 20
        and summary["chineseIdentitySummaries"] == 20
        and summary["top10ChineseIdentitySummaries"] == 10
        and summary["top10ChineseCoreValues"] == 10
        and all(summary[field] == 0 for field in zero_fields)
    )
    return {
        "schemaVersion": 1,
        "status": "PASS" if passed else "FAIL",
        "sourceGenerationId": today.generationId,
        "servingGenerationId": today.servingGenerationId,
        "servingSchemaVersion": today.schemaVersion,
        "summary": summary,
        "projects": entries,
    }
