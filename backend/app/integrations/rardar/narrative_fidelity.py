"""Read-only author-narrative boundary audit for validated Rardar Serving data."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

from app.integrations.rardar.serving import ServingProjectionLoader
from app.integrations.rardar.serving_schemas import ServingProjectDetail

_NARRATIVE_REF = re.compile(r"^readme:narrative:highlight:(\d+)$")
_EXPECTED_SOURCE_LABEL = {
    "official_zh": "官方中文 README",
    "official_translated": "官方 README（译）",
    "rardar_derived": "Rardar 整理",
    "insufficient": "受限概括",
}


def _semantic_key(value: str | None) -> str:
    return re.sub(r"[^0-9a-z\u3400-\u9fff]+", "", (value or "").casefold())


def _same_claim(left: str | None, right: str | None) -> bool:
    first, second = _semantic_key(left), _semantic_key(right)
    return bool(first and second and first == second)


def _source_orders(detail: ServingProjectDetail) -> list[int]:
    orders: list[int] = []
    for reference in detail.evidence.evidenceIndex:
        match = _NARRATIVE_REF.fullmatch(reference)
        if match:
            orders.append(int(match.group(1)))
    return sorted(orders)


def _audit_project(detail: ServingProjectDetail) -> dict[str, Any]:
    profile = detail.profile
    mode = profile.officialNarrativeMode
    source_orders = _source_orders(detail)
    rendered_orders = [highlight.sourceOrder for highlight in profile.officialHighlights]
    source_titles = [highlight.sourceTitle for highlight in profile.officialHighlights]
    rendered_titles = [highlight.titleZh for highlight in profile.officialHighlights]
    violations: list[str] = []

    is_official = mode in {"official_zh", "official_translated"}
    if mode == "official_zh" and source_titles != rendered_titles:
        violations.append("official_highlight_title_rewritten")
    expected_orders = list(range(1, len(rendered_orders) + 1))
    if is_official and (rendered_orders != expected_orders or (source_orders and rendered_orders != source_orders)):
        violations.append("official_highlight_order_changed")
    if mode == "official_translated" and len(source_orders) != len(rendered_orders):
        violations.append("translated_highlight_count_changed")
    if mode == "official_translated" and source_orders != rendered_orders:
        violations.append("translated_highlight_order_changed")
    if mode is not None and profile.sourceLabel != _EXPECTED_SOURCE_LABEL[mode]:
        violations.append("official_source_falsely_labeled")
    if _same_claim(profile.officialTaglineZh, profile.rardarAssessmentZh):
        violations.append("official_tagline_replaced_by_assessment")
    if _same_claim(profile.officialPositioningZh, profile.rardarAssessmentZh):
        violations.extend(
            [
                "rardar_assessment_as_official_positioning",
                "official_positioning_replaced_by_keyword_template",
            ]
        )
    official_claims = {
        (_semantic_key(highlight.titleZh), _semantic_key(highlight.detailZh))
        for highlight in profile.officialHighlights
    }
    differentiator_claims = {
        (_semantic_key(item.title), _semantic_key(item.detail)) for item in profile.rardarDifferentiators
    }
    if is_official and official_claims.intersection(differentiator_claims):
        violations.append("rardar_differentiator_as_official_highlight")
    violations = list(dict.fromkeys(violations))

    return {
        "repository": profile.repository,
        "narrativeMode": mode,
        "taglineSource": profile.officialTaglineEvidenceRefs,
        "positioningSource": profile.officialPositioningEvidenceRefs,
        "highlightCount": len(profile.officialHighlights),
        "sourceHighlightTitles": source_titles,
        "renderedHighlightTitles": rendered_titles,
        "sourceOrder": source_orders,
        "renderedOrder": rendered_orders,
        "rardarAssessmentPresent": profile.rardarAssessmentZh is not None,
        "boundaryViolations": violations,
        "recommendedRepair": "none" if not violations else "rebuild_from_versioned_official_narrative",
    }


def audit_official_narrative(target: Path) -> dict[str, Any]:
    """Audit one current immutable Serving generation without network or model calls."""

    loader = ServingProjectionLoader(target)
    today, _etag = loader.load_today_with_etag()
    projects: list[dict[str, Any]] = []
    for project in today.exactRanked[:20]:
        detail, _etag = loader.load_project_with_etag(project.githubRepositoryId, today.generationId)
        projects.append(_audit_project(detail))

    modes = Counter(project["narrativeMode"] for project in projects)
    violations = Counter(violation for project in projects for violation in project["boundaryViolations"])
    summary = {
        "total": len(projects),
        "officialZh": modes["official_zh"],
        "officialTranslated": modes["official_translated"],
        "rardarDerived": modes["rardar_derived"],
        "insufficient": modes["insufficient"],
        "titleRewriteViolations": violations["official_highlight_title_rewritten"],
        "orderViolations": violations["official_highlight_order_changed"],
        "officialRardarBoundaryViolations": sum(
            count
            for code, count in violations.items()
            if code
            in {
                "rardar_assessment_as_official_positioning",
                "rardar_differentiator_as_official_highlight",
                "official_tagline_replaced_by_assessment",
                "official_positioning_replaced_by_keyword_template",
                "official_source_falsely_labeled",
            }
        ),
        "translationCountViolations": violations["translated_highlight_count_changed"],
        "translationOrderViolations": violations["translated_highlight_order_changed"],
    }
    return {
        "schemaVersion": 1,
        "status": "PASS" if not violations else "FAIL",
        "sourceGenerationId": today.generationId,
        "servingGenerationId": today.servingGenerationId,
        "servingSchemaVersion": today.schemaVersion,
        "summary": summary,
        "violationCounts": dict(sorted(violations.items())),
        "projects": projects,
    }
