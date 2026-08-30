"""Read-only field-level positioning audit for immutable Rardar Serving data."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

from app.integrations.rardar.serving import ServingProjectionLoader
from app.integrations.rardar.serving_profiles import (
    _official_chinese_positioning,
    _official_positioning_is_high_signal,
)
from app.integrations.rardar.serving_schemas import ServingProjectDetail

_LEAKAGE_PATTERNS = {
    "operation": re.compile(
        r"(?:默认启动|启动\s*(?:Web\s*UI|服务)|仅启动服务器|运行命令|安装命令|"
        r"127\.0\.0\.1|localhost|端口(?:号)?|\b(?:npm|pnpm|yarn|pip|docker)\s+(?:run|install))",
        re.IGNORECASE,
    ),
    "deployment": re.compile(r"(?:SSH\s*暴露|暴露.{0,20}(?:URL|服务)|部署流程|server[- ]?only)", re.IGNORECASE),
    "validation": re.compile(
        r"(?:最终\s*Git\s*diff|FastAPI\s*(?:与|和|/)?\s*React\s*仓库|"
        r"Claude\s*Code\s*会话|benchmark\s*测量|通过.{0,24}(?:验证|测量))",
        re.IGNORECASE,
    ),
    "example": re.compile(r"(?:例如|举例|示例中|具体用例)", re.IGNORECASE),
}
_GENERIC_SUBJECT = re.compile(r"^(?:该项目是|该仓库是|本项目是|这个项目是|这是一个|这是一套)")


def _source_claim(detail: ServingProjectDetail) -> str | None:
    profile = detail.profile
    if profile.positioningSourceMode != "official_zh" or len(profile.positioningEvidenceRefs) != 1:
        return None
    raw = detail.evidence.evidenceIndex.get(profile.positioningEvidenceRefs[0])
    if raw is None:
        return None
    return raw.split(": ", 1)[1] if ": " in raw else raw


def _audit_project(detail: ServingProjectDetail, *, require_complete: bool = False) -> dict[str, Any]:
    profile = detail.profile
    text = profile.positioningZh or ""
    leakages = {role: bool(pattern.search(text)) for role, pattern in _LEAKAGE_PATTERNS.items()}
    repository_subject = profile.repository.rsplit("/", 1)[-1]
    subject_duplication = bool(
        profile.positioningSourceMode == "rardar_derived"
        and (_GENERIC_SUBJECT.match(text) or re.match(rf"^{re.escape(repository_subject)}\s+是", text, re.IGNORECASE))
    )
    source_claim = _source_claim(detail)
    official_quote_modified = bool(
        profile.positioningSourceMode == "official_zh"
        and (source_claim is None or _official_chinese_positioning(source_claim) != text)
    )
    positioning_low_signal = bool(
        profile.positioningSourceMode != "insufficient" and not _official_positioning_is_high_signal(text, "zh")
    )
    violations = [f"{role}_leakage" for role, leaked in leakages.items() if leaked]
    if subject_duplication:
        violations.append("subject_duplication")
    if official_quote_modified:
        violations.append("official_quote_modified")
    if positioning_low_signal:
        violations.append("positioning_low_signal")
    if profile.positioningSourceMode == "insufficient":
        if text or profile.positioningEvidenceRefs or profile.positioningIncludedRoles:
            violations.append("insufficient_positioning_exposed")
        if require_complete:
            violations.append("positioning_missing")
    elif not text or not profile.positioningEvidenceRefs or not profile.positioningIncludedRoles:
        violations.append("positioning_contract_incomplete")

    return {
        "repository": profile.repository,
        "positioningZh": profile.positioningZh,
        "positioningSourceMode": profile.positioningSourceMode,
        "positioningEvidenceRefs": profile.positioningEvidenceRefs,
        "includedRoles": profile.positioningIncludedRoles,
        "excludedRoles": [clause.role for clause in profile.positioningExcludedClauses],
        "excludedClauses": [clause.model_dump(mode="json") for clause in profile.positioningExcludedClauses],
        "operationLeakage": leakages["operation"],
        "deploymentLeakage": leakages["deployment"],
        "validationLeakage": leakages["validation"],
        "exampleLeakage": leakages["example"],
        "subjectDuplication": subject_duplication,
        "officialQuoteModified": official_quote_modified,
        "positioningLowSignal": positioning_low_signal,
        "qualityResult": "PASS" if not violations else "FAIL",
        "violations": violations,
    }


def audit_positioning_precision(target: Path) -> dict[str, Any]:
    """Audit current Top 20 positioning without GitHub, model, or raw-generation reads."""

    loader = ServingProjectionLoader(target)
    today, _etag = loader.load_today_with_etag()
    projects: list[dict[str, Any]] = []
    require_complete = bool(today.coverage is not None and today.coverage.exactCount >= 20)
    for project in today.exactRanked[:20]:
        detail, _etag = loader.load_project_with_etag(project.githubRepositoryId, today.generationId)
        projects.append(_audit_project(detail, require_complete=require_complete))
    modes = Counter(project["positioningSourceMode"] for project in projects)
    violations = Counter(violation for project in projects for violation in project["violations"])
    return {
        "schemaVersion": 1,
        "status": "PASS" if not violations else "FAIL",
        "sourceGenerationId": today.generationId,
        "servingGenerationId": today.servingGenerationId,
        "servingSchemaVersion": today.schemaVersion,
        "summary": {
            "total": len(projects),
            "officialZh": modes["official_zh"],
            "officialTranslated": modes["official_translated"],
            "rardarDerived": modes["rardar_derived"],
            "insufficient": modes["insufficient"],
            "operationLeakage": violations["operation_leakage"],
            "deploymentLeakage": violations["deployment_leakage"],
            "validationLeakage": violations["validation_leakage"],
            "exampleLeakage": violations["example_leakage"],
            "subjectDuplication": violations["subject_duplication"],
            "officialQuoteModified": violations["official_quote_modified"],
            "positioningLowSignal": violations["positioning_low_signal"],
            "remainingIssues": sum(violations.values()),
        },
        "violationCounts": dict(sorted(violations.items())),
        "projects": projects,
    }
