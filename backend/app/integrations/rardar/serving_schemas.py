"""Strict, versioned DTOs for Rardar's immutable local serving projection."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

from app.integrations.rardar.schemas import (
    ExactExplosionProject,
    ExplosionCoverage,
    ExplosionSourceStatus,
    ExplosionWindow,
    PendingExplosionProject,
)


class StrictServingModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


ProfileState = Literal["complete", "partial", "source_unavailable"]
ProfileQualityState = Literal["ready", "partial", "rejected"]
OfficialNarrativeMode = Literal["official_zh", "official_translated", "rardar_derived", "insufficient"]
PositioningSourceMode = Literal["official_zh", "official_translated", "rardar_derived", "insufficient"]
CapabilitySourceMode = Literal[
    "official_zh",
    "official_translated",
    "rardar_derived",
    "deterministic_fallback",
]
PositioningIncludedRole = Literal["identity", "core_mechanism", "primary_outcome"]
PositioningExcludedRole = Literal["operation", "deployment", "validation", "example", "boundary"]
OfficialNarrativeIssue = Literal[
    "tagline_missing",
    "positioning_missing",
    "highlights_missing",
    "highlight_title_missing",
    "highlight_order_unverified",
    "translation_pending",
    "source_structure_weak",
    "official_narrative_insufficient",
]
ProfileSourceLabel = Literal[
    "官方中文 README",
    "官方 README（译）",
    "GitHub Description",
    "官方原文",
    "受限概括",
    "Rardar 整理",
]
TranslationState = Literal["not_needed", "translated", "pending", "unavailable"]


def _normalized_capability_text(value: str) -> str:
    return re.sub(r"[^0-9a-z\u3400-\u9fff]+", "", value.casefold())


def _normalized_primary_text(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip()
    cleaned = re.sub(
        r"^(?:这是|它是|该项目是|该仓库是|本项目是|本仓库是|作为|是)?\s*(?:一个|一种|一款|一套|一项)?\s*",
        "",
        cleaned,
    )
    cleaned = re.sub(r"(?:这是|它是|该项目|该仓库|本项目|本仓库|公开发布|进行|面向|项目|的)", "", cleaned)
    return re.sub(r"[^0-9a-z\u3400-\u9fff]+", "", cleaned.casefold())


def _primary_texts_duplicate(identity: str, positioning: str) -> bool:
    first = _normalized_primary_text(identity)
    second = _normalized_primary_text(positioning)
    if not first or not second:
        return False
    shorter, longer = sorted((len(first), len(second)))
    return first == second or (shorter >= 8 and longer <= int(shorter * 1.35) and (first in second or second in first))


class ServingCapability(StrictServingModel):
    """One complete, evidence-bound capability for both Today and project detail."""

    title: str = Field(min_length=2, max_length=32)
    detail: str = Field(min_length=4, max_length=1200)
    shortDetail: str | None = Field(default=None, min_length=4, max_length=200)
    evidenceRefs: list[str] = Field(min_length=1, max_length=12)
    sourceMode: CapabilitySourceMode | None = None

    @field_validator("title", "detail", "shortDetail")
    @classmethod
    def validate_complete_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        cleaned = re.sub(r"\s+", " ", value).strip()
        if not cleaned or cleaned.endswith(("…", "...")):
            raise ValueError("capability text must be complete")
        return cleaned

    @field_validator("title")
    @classmethod
    def validate_title_width(cls, value: str) -> str:
        if len(re.findall(r"[\u3400-\u9fff]", value)) > 16:
            raise ValueError("Chinese capability title is too long")
        return value

    @field_validator("evidenceRefs")
    @classmethod
    def validate_evidence_refs(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values) or any(not value.strip() or len(value) > 240 for value in values):
            raise ValueError("capability evidence refs must be unique and bounded")
        return values

    @model_validator(mode="after")
    def validate_title_detail_separation(self) -> ServingCapability:
        title = _normalized_capability_text(self.title)
        detail = _normalized_capability_text(self.detail)
        if title == detail or (title and detail.startswith(title)):
            raise ValueError("capability detail must not repeat its title")
        if self.shortDetail is not None and _normalized_capability_text(self.shortDetail) == title:
            raise ValueError("capability short detail must explain its title")
        return self


class OfficialHighlight(StrictServingModel):
    """One author-ordered README highlight and its faithful Chinese rendering."""

    sourceOrder: int = Field(ge=1, le=8)
    sourceTitle: str = Field(min_length=1, max_length=200)
    sourceDetail: str = Field(min_length=1, max_length=1200)
    titleZh: str = Field(min_length=1, max_length=200)
    detailZh: str = Field(min_length=1, max_length=1200)
    evidenceRefs: list[str] = Field(min_length=1, max_length=12)

    @field_validator("sourceTitle", "sourceDetail", "titleZh", "detailZh")
    @classmethod
    def validate_complete_text(cls, value: str) -> str:
        cleaned = re.sub(r"\s+", " ", value).strip()
        if not cleaned or cleaned.endswith(("…", "...")):
            raise ValueError("official highlight text must be complete")
        return cleaned

    @field_validator("evidenceRefs")
    @classmethod
    def validate_evidence_refs(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values) or any(not value.strip() or len(value) > 240 for value in values):
            raise ValueError("official highlight evidence refs must be unique and bounded")
        return values


class PositioningExcludedClause(StrictServingModel):
    """One evidence-bound clause deliberately excluded from the primary positioning."""

    role: PositioningExcludedRole
    text: str = Field(min_length=1, max_length=1200)
    evidenceRefs: list[str] = Field(min_length=1, max_length=12)

    @field_validator("text")
    @classmethod
    def validate_complete_text(cls, value: str) -> str:
        cleaned = re.sub(r"\s+", " ", value).strip()
        if not cleaned or cleaned.endswith(("…", "...")):
            raise ValueError("excluded positioning clause must be complete")
        return cleaned

    @field_validator("evidenceRefs")
    @classmethod
    def validate_evidence_refs(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values) or any(not value.strip() or len(value) > 240 for value in values):
            raise ValueError("excluded positioning evidence refs must be unique and bounded")
        return values


class ServingFile(StrictServingModel):
    path: str = Field(pattern=r"^[A-Za-z0-9._/-]+\.json$")
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    bytes: int = Field(ge=2, le=4 * 1024 * 1024)


class ServingProfileSummary(StrictServingModel):
    total: int = Field(ge=0, le=20)
    complete: int = Field(ge=0, le=20)
    partial: int = Field(ge=0, le=20)
    sourceUnavailable: int = Field(ge=0, le=20)
    chineseSummaries: int = Field(ge=0, le=20)
    qualityReady: int = Field(default=0, ge=0, le=20)
    qualityPartial: int = Field(default=0, ge=0, le=20)
    qualityRejected: int = Field(default=0, ge=0, le=20)
    officialZh: int = Field(default=0, ge=0, le=20)
    officialTranslated: int = Field(default=0, ge=0, le=20)
    rardarDerived: int = Field(default=0, ge=0, le=20)
    insufficient: int = Field(default=0, ge=0, le=20)

    @model_validator(mode="after")
    def validate_counts(self) -> ServingProfileSummary:
        if self.complete + self.partial + self.sourceUnavailable != self.total:
            raise ValueError("profile state counts must equal total")
        if self.chineseSummaries > self.total:
            raise ValueError("Chinese summary count cannot exceed total")
        quality_total = self.qualityReady + self.qualityPartial + self.qualityRejected
        if quality_total not in {0, self.total}:
            raise ValueError("profile quality counts must be absent or equal total")
        narrative_total = self.officialZh + self.officialTranslated + self.rardarDerived + self.insufficient
        if narrative_total not in {0, self.total}:
            raise ValueError("profile narrative counts must be absent or equal total")
        return self


class ServingPointer(StrictServingModel):
    schemaVersion: Literal[1, 2, 3, 4, 5, 6, 7]
    servingGenerationId: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{1,190}$")
    sourceGenerationId: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{1,126}$")
    manifestSha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    activatedAt: AwareDatetime


class ServingManifest(StrictServingModel):
    schemaVersion: Literal[1, 2, 3, 4, 5, 6, 7]
    state: Literal["ready"]
    servingGenerationId: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{1,190}$")
    sourceGenerationId: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{1,126}$")
    sourceManifestSha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    sourceExplosionSha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    today: ServingFile
    projects: dict[str, ServingFile] = Field(max_length=20)
    evidence: dict[str, ServingFile] = Field(max_length=20)
    generatedAt: AwareDatetime
    profileSummary: ServingProfileSummary

    @model_validator(mode="after")
    def validate_inventory(self) -> ServingManifest:
        if set(self.projects) != set(self.evidence):
            raise ValueError("project and evidence inventories must match")
        if len(self.projects) != self.profileSummary.total:
            raise ValueError("profile inventory must match summary")
        return self


class TodayProject(ExactExplosionProject):
    profileState: ProfileState
    officialSummaryZh: str = Field(min_length=1, max_length=2000)
    sourceLabel: ProfileSourceLabel
    sourceLanguage: str | None = Field(default=None, max_length=32)
    capabilityBulletsZh: list[str] = Field(max_length=4)
    capabilities: list[ServingCapability] = Field(default_factory=list, max_length=4)
    translationState: TranslationState
    identitySummaryZh: str | None = Field(default=None, min_length=1, max_length=600)
    coreValueZh: str | None = Field(default=None, min_length=12, max_length=240)
    coreValueEvidenceRefs: list[str] = Field(default_factory=list, max_length=12)
    keyDifferentiators: list[ServingCapability] = Field(default_factory=list, max_length=2)
    productFormsZh: list[str] = Field(default_factory=list, max_length=3)
    qualityState: ProfileQualityState | None = None
    qualityIssues: list[str] = Field(default_factory=list, max_length=24)
    officialTaglineZh: str | None = Field(default=None, min_length=1, max_length=600)
    officialTaglineEvidenceRefs: list[str] = Field(default_factory=list, max_length=12)
    officialPositioningZh: str | None = Field(default=None, min_length=1, max_length=2000)
    officialPositioningEvidenceRefs: list[str] = Field(default_factory=list, max_length=12)
    positioningZh: str | None = Field(default=None, min_length=1, max_length=2000)
    positioningSourceMode: PositioningSourceMode | None = None
    positioningEvidenceRefs: list[str] = Field(default_factory=list, max_length=12)
    positioningIncludedRoles: list[PositioningIncludedRole] = Field(default_factory=list, max_length=3)
    positioningExcludedClauses: list[PositioningExcludedClause] = Field(default_factory=list, max_length=12)
    officialHighlights: list[OfficialHighlight] = Field(default_factory=list, max_length=8)
    officialNarrativeMode: OfficialNarrativeMode | None = None
    officialNarrativeIssues: list[OfficialNarrativeIssue] = Field(default_factory=list, max_length=12)
    rardarAssessmentZh: str | None = Field(default=None, min_length=12, max_length=600)
    rardarAssessmentEvidenceRefs: list[str] = Field(default_factory=list, max_length=12)
    rardarDifferentiators: list[ServingCapability] = Field(default_factory=list, max_length=2)


class ServingTodaySnapshot(StrictServingModel):
    schemaVersion: Literal[1, 2, 3, 4, 5, 6, 7]
    state: Literal["ready", "warming_up", "baseline_missing", "not_ready"]
    reason: Literal["explosion_artifact_not_published"] | None = None
    generationId: str
    publishedAt: AwareDatetime
    capturedAt: AwareDatetime | None
    window: ExplosionWindow | None
    coverage: ExplosionCoverage | None
    exactRanked: list[TodayProject] = Field(max_length=20)
    pendingRanked: list[PendingExplosionProject] = Field(max_length=20)
    conflictCount: int = Field(ge=0, le=500)
    sourceStatus: ExplosionSourceStatus | None
    dataMode: Literal["real", "demo"] = "real"
    dataLabel: str = "Rardar 已验证 Serving 快照"
    syncedAt: AwareDatetime | None = None
    sourceHost: str | None = Field(default=None, max_length=100)
    manifestSha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    artifactSha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    servingGenerationId: str
    profileSummary: ServingProfileSummary

    @model_validator(mode="after")
    def validate_v4_quality_projection(self) -> ServingTodaySnapshot:
        if self.schemaVersion >= 4:
            for project in self.exactRanked:
                if project.identitySummaryZh is None or project.qualityState is None:
                    raise ValueError("Serving v4 requires projected profile quality")
                if project.identitySummaryZh != project.officialSummaryZh:
                    raise ValueError("Serving v4 identity projection is inconsistent")
                if len(set(project.qualityIssues)) != len(project.qualityIssues) or any(
                    not issue or len(issue) > 80 for issue in project.qualityIssues
                ):
                    raise ValueError("Serving v4 quality issues must be unique and bounded")
                if project.coreValueZh is not None and not project.coreValueEvidenceRefs:
                    raise ValueError("Serving v4 core value requires evidence")
                if project.qualityState == "ready" and (
                    project.coreValueZh is None
                    or not project.keyDifferentiators
                    or not project.capabilities
                    or project.qualityIssues
                ):
                    raise ValueError("Serving v4 ready project is incomplete")
                if project.qualityState == "rejected" and (
                    project.coreValueZh is not None
                    or project.keyDifferentiators
                    or project.capabilities
                    or not project.qualityIssues
                ):
                    raise ValueError("Serving v4 rejected project exposes unsafe claims")
            actual_quality = {
                "ready": sum(project.qualityState == "ready" for project in self.exactRanked),
                "partial": sum(project.qualityState == "partial" for project in self.exactRanked),
                "rejected": sum(project.qualityState == "rejected" for project in self.exactRanked),
            }
            if (
                self.profileSummary.qualityReady != actual_quality["ready"]
                or self.profileSummary.qualityPartial != actual_quality["partial"]
                or self.profileSummary.qualityRejected != actual_quality["rejected"]
            ):
                raise ValueError("Serving v4 quality summary is inconsistent")
        if self.schemaVersion >= 5:
            for project in self.exactRanked:
                _validate_v5_narrative(project)
                if self.schemaVersion >= 6:
                    _validate_v6_positioning(project)
            narrative_counts = {
                "official_zh": sum(project.officialNarrativeMode == "official_zh" for project in self.exactRanked),
                "official_translated": sum(
                    project.officialNarrativeMode == "official_translated" for project in self.exactRanked
                ),
                "rardar_derived": sum(
                    project.officialNarrativeMode == "rardar_derived" for project in self.exactRanked
                ),
                "insufficient": sum(project.officialNarrativeMode == "insufficient" for project in self.exactRanked),
            }
            if (
                self.profileSummary.officialZh != narrative_counts["official_zh"]
                or self.profileSummary.officialTranslated != narrative_counts["official_translated"]
                or self.profileSummary.rardarDerived != narrative_counts["rardar_derived"]
                or self.profileSummary.insufficient != narrative_counts["insufficient"]
            ):
                raise ValueError("Serving v5 narrative summary is inconsistent")
        if (
            self.schemaVersion >= 7
            and len(self.exactRanked) == 20
            and any(
                not project.capabilities or any(item.sourceMode is None for item in project.capabilities)
                for project in self.exactRanked
            )
        ):
            raise ValueError("Serving v7 exact Top 20 requires sourced capabilities")
        return self


class ReadmeSection(StrictServingModel):
    heading: str = Field(min_length=1, max_length=200)
    path: str = Field(min_length=1, max_length=500)
    purpose: Literal[
        "overview",
        "capabilities",
        "use_cases",
        "quick_start",
        "architecture",
        "examples",
        "other",
    ]
    excerpts: list[str] = Field(max_length=4)
    listItems: list[str] = Field(max_length=8)
    evidenceRefs: list[str] = Field(min_length=1, max_length=12)


class StartHereLink(StrictServingModel):
    label: str = Field(min_length=1, max_length=200)
    path: str = Field(min_length=1, max_length=500)
    htmlUrl: HttpUrl
    evidenceRefs: list[str] = Field(min_length=1, max_length=6)


class OfficialProjectProfile(StrictServingModel):
    profileSchemaVersion: Literal[
        "rardar-project-profile-v1",
        "rardar-project-profile-v2",
        "rardar-project-profile-v3",
        "rardar-project-profile-v4",
        "rardar-project-profile-v5",
        "rardar-project-profile-v6",
        "rardar-project-profile-v7",
    ]
    promptVersion: Literal[
        "rardar-project-profile-zh-v1",
        "rardar-project-profile-zh-v2",
        "rardar-project-profile-zh-v3",
        "rardar-project-profile-zh-v4",
        "rardar-project-profile-zh-v5",
        "rardar-project-profile-zh-v6",
        "rardar-project-profile-zh-v7",
        "rardar-project-profile-zh-v8",
        "rardar-project-profile-zh-v9",
        "rardar-project-profile-zh-v10",
        "rardar-project-profile-zh-v11",
        "rardar-project-profile-zh-v12",
        "rardar-project-profile-zh-v13",
        "rardar-project-profile-zh-v14",
        "rardar-project-profile-zh-v15",
    ]
    githubRepositoryId: int = Field(gt=0)
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    htmlUrl: HttpUrl
    generationId: str
    profileState: ProfileState
    officialSummaryZh: str = Field(min_length=1, max_length=2000)
    sourceLabel: ProfileSourceLabel
    sourceLanguage: str | None = Field(default=None, max_length=32)
    capabilityBulletsZh: list[str] = Field(max_length=8)
    capabilities: list[ServingCapability] = Field(default_factory=list, max_length=8)
    productFormsZh: list[str] = Field(default_factory=list, max_length=6)
    supportedEnvironmentsZh: list[str] = Field(default_factory=list, max_length=12)
    primaryUseCasesZh: list[str] = Field(max_length=8)
    deliveryFormsZh: list[str] = Field(max_length=8)
    claimEvidenceRefs: dict[str, list[str]] = Field(max_length=64)
    readmePath: str | None = Field(default=None, max_length=500)
    readmeBlobSha: str | None = Field(default=None, pattern=r"^[A-Fa-f0-9]{7,64}$")
    selectedSections: list[ReadmeSection] = Field(max_length=12)
    originalExcerpts: list[str] = Field(max_length=12)
    startHere: list[StartHereLink] = Field(max_length=12)
    evidenceDigest: str = Field(pattern=r"^[a-f0-9]{64}$")
    generatedAt: AwareDatetime
    translationState: TranslationState
    identitySummaryZh: str | None = Field(default=None, min_length=1, max_length=600)
    coreValueZh: str | None = Field(default=None, min_length=12, max_length=240)
    coreValueEvidenceRefs: list[str] = Field(default_factory=list, max_length=12)
    keyDifferentiators: list[ServingCapability] = Field(default_factory=list, max_length=2)
    qualityState: ProfileQualityState | None = None
    qualityIssues: list[str] = Field(default_factory=list, max_length=24)
    officialTaglineZh: str | None = Field(default=None, min_length=1, max_length=600)
    officialTaglineEvidenceRefs: list[str] = Field(default_factory=list, max_length=12)
    officialPositioningZh: str | None = Field(default=None, min_length=1, max_length=2000)
    officialPositioningEvidenceRefs: list[str] = Field(default_factory=list, max_length=12)
    positioningZh: str | None = Field(default=None, min_length=1, max_length=2000)
    positioningSourceMode: PositioningSourceMode | None = None
    positioningEvidenceRefs: list[str] = Field(default_factory=list, max_length=12)
    positioningIncludedRoles: list[PositioningIncludedRole] = Field(default_factory=list, max_length=3)
    positioningExcludedClauses: list[PositioningExcludedClause] = Field(default_factory=list, max_length=12)
    officialHighlights: list[OfficialHighlight] = Field(default_factory=list, max_length=8)
    officialNarrativeMode: OfficialNarrativeMode | None = None
    officialNarrativeIssues: list[OfficialNarrativeIssue] = Field(default_factory=list, max_length=12)
    officialNarrativePromptVersion: str | None = Field(default=None, max_length=80)
    rardarAssessmentZh: str | None = Field(default=None, min_length=12, max_length=600)
    rardarAssessmentEvidenceRefs: list[str] = Field(default_factory=list, max_length=12)
    rardarDifferentiators: list[ServingCapability] = Field(default_factory=list, max_length=2)
    rardarAssessmentPromptVersion: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def validate_structured_capabilities(self) -> OfficialProjectProfile:
        if (
            self.profileSchemaVersion
            in {
                "rardar-project-profile-v3",
                "rardar-project-profile-v4",
                "rardar-project-profile-v5",
                "rardar-project-profile-v6",
                "rardar-project-profile-v7",
            }
            and [item.detail for item in self.capabilities] != self.capabilityBulletsZh
        ):
            raise ValueError("structured capabilities must project to legacy capability details")
        if self.profileSchemaVersion in {
            "rardar-project-profile-v4",
            "rardar-project-profile-v5",
            "rardar-project-profile-v6",
            "rardar-project-profile-v7",
        }:
            if self.identitySummaryZh is None or self.qualityState is None:
                raise ValueError("profile v4 requires identity and quality state")
            if self.officialSummaryZh != self.identitySummaryZh:
                raise ValueError("legacy summary must project from identity summary")
            if len(set(self.qualityIssues)) != len(self.qualityIssues) or any(
                not issue or len(issue) > 80 for issue in self.qualityIssues
            ):
                raise ValueError("profile quality issues must be unique and bounded")
            if self.qualityState == "ready" and (
                self.coreValueZh is None
                or not self.coreValueEvidenceRefs
                or not self.keyDifferentiators
                or not self.capabilities
                or self.qualityIssues
            ):
                raise ValueError("ready profile requires evidence-backed semantic layers")
            if self.coreValueZh is not None and not self.coreValueEvidenceRefs:
                raise ValueError("profile core value requires evidence")
            if self.qualityState == "rejected" and (
                self.coreValueZh is not None or self.keyDifferentiators or self.capabilities
            ):
                raise ValueError("rejected profile must not expose rejected semantic claims")
            if self.qualityState == "rejected" and not self.qualityIssues:
                raise ValueError("rejected profile requires a stable quality reason")
        if self.profileSchemaVersion in {
            "rardar-project-profile-v5",
            "rardar-project-profile-v6",
            "rardar-project-profile-v7",
        }:
            _validate_v5_narrative(self)
            if self.officialNarrativePromptVersion is None or self.rardarAssessmentPromptVersion is None:
                raise ValueError("profile v5 requires both narrative prompt versions")
        if self.profileSchemaVersion in {"rardar-project-profile-v6", "rardar-project-profile-v7"}:
            _validate_v6_positioning(self)
        if self.profileSchemaVersion == "rardar-project-profile-v7" and any(
            item.sourceMode is None for item in self.capabilities
        ):
            raise ValueError("profile v7 requires sourced capabilities")
        return self


class ProjectEvidenceProjection(StrictServingModel):
    schemaVersion: Literal[1]
    githubRepositoryId: int = Field(gt=0)
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    generationId: str
    readmePath: str | None = Field(default=None, max_length=500)
    readmeBlobSha: str | None = Field(default=None, pattern=r"^[A-Fa-f0-9]{7,64}$")
    sourceLanguage: str | None = Field(default=None, max_length=32)
    selectedSections: list[ReadmeSection] = Field(max_length=12)
    originalExcerpts: list[str] = Field(max_length=12)
    topLevelTree: list[dict[str, str]] = Field(max_length=100)
    evidenceIndex: dict[str, str] = Field(max_length=240)
    pathRefs: dict[str, str] = Field(max_length=240)
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class ServingProjectDetail(StrictServingModel):
    schemaVersion: Literal[1, 2, 3, 4, 5, 6, 7]
    generationId: str
    servingGenerationId: str
    project: TodayProject
    profile: OfficialProjectProfile
    evidence: ProjectEvidenceProjection
    coverage: ExplosionCoverage | None = None
    conflictCount: int = Field(default=0, ge=0, le=500)

    @model_validator(mode="after")
    def validate_identity(self) -> ServingProjectDetail:
        identities = {
            (self.project.githubRepositoryId, self.project.repository),
            (self.profile.githubRepositoryId, self.profile.repository),
            (self.evidence.githubRepositoryId, self.evidence.repository),
        }
        if len(identities) != 1:
            raise ValueError("project identity is inconsistent")
        if {self.generationId, self.profile.generationId, self.evidence.generationId} != {self.generationId}:
            raise ValueError("project generation is inconsistent")
        if self.profile.evidenceDigest != self.evidence.digest:
            raise ValueError("project evidence digest is inconsistent")
        return self


class ServingProjectRecord(StrictServingModel):
    schemaVersion: Literal[1, 2, 3, 4, 5, 6, 7]
    generationId: str
    servingGenerationId: str
    project: TodayProject
    profile: OfficialProjectProfile
    coverage: ExplosionCoverage | None = None
    conflictCount: int = Field(default=0, ge=0, le=500)

    @model_validator(mode="after")
    def validate_identity(self) -> ServingProjectRecord:
        if self.generationId != self.profile.generationId:
            raise ValueError("project generation is inconsistent")
        if (
            self.project.githubRepositoryId != self.profile.githubRepositoryId
            or self.project.repository != self.profile.repository
            or self.project.htmlUrl != self.profile.htmlUrl
        ):
            raise ValueError("project identity is inconsistent")
        if (
            self.project.profileState != self.profile.profileState
            or self.project.officialSummaryZh != self.profile.officialSummaryZh
            or self.project.sourceLabel != self.profile.sourceLabel
            or self.project.sourceLanguage != self.profile.sourceLanguage
            or self.project.capabilityBulletsZh != self.profile.capabilityBulletsZh[:4]
            or self.project.capabilities != self.profile.capabilities[:4]
            or self.project.translationState != self.profile.translationState
            or self.project.identitySummaryZh != self.profile.identitySummaryZh
            or self.project.coreValueZh != self.profile.coreValueZh
            or self.project.coreValueEvidenceRefs != self.profile.coreValueEvidenceRefs
            or self.project.keyDifferentiators != self.profile.keyDifferentiators
            or self.project.productFormsZh != self.profile.productFormsZh[:3]
            or self.project.qualityState != self.profile.qualityState
            or self.project.qualityIssues != self.profile.qualityIssues
            or self.project.officialTaglineZh != self.profile.officialTaglineZh
            or self.project.officialTaglineEvidenceRefs != self.profile.officialTaglineEvidenceRefs
            or self.project.officialPositioningZh != self.profile.officialPositioningZh
            or self.project.officialPositioningEvidenceRefs != self.profile.officialPositioningEvidenceRefs
            or self.project.positioningZh != self.profile.positioningZh
            or self.project.positioningSourceMode != self.profile.positioningSourceMode
            or self.project.positioningEvidenceRefs != self.profile.positioningEvidenceRefs
            or self.project.positioningIncludedRoles != self.profile.positioningIncludedRoles
            or self.project.positioningExcludedClauses != self.profile.positioningExcludedClauses
            or self.project.officialHighlights != self.profile.officialHighlights
            or self.project.officialNarrativeMode != self.profile.officialNarrativeMode
            or self.project.officialNarrativeIssues != self.profile.officialNarrativeIssues
            or self.project.rardarAssessmentZh != self.profile.rardarAssessmentZh
            or self.project.rardarAssessmentEvidenceRefs != self.profile.rardarAssessmentEvidenceRefs
            or self.project.rardarDifferentiators != self.profile.rardarDifferentiators
        ):
            raise ValueError("project profile projection is inconsistent")
        return self


def _validate_v5_narrative(value: TodayProject | OfficialProjectProfile) -> None:
    mode = value.officialNarrativeMode
    if mode is None:
        raise ValueError("Serving v5 requires an official narrative mode")
    expected_source_labels = {
        "official_zh": "官方中文 README",
        "official_translated": "官方 README（译）",
        "rardar_derived": "Rardar 整理",
        "insufficient": "受限概括",
    }
    if value.sourceLabel != expected_source_labels[mode]:
        raise ValueError("Serving v5 narrative source label is invalid")
    issues = value.officialNarrativeIssues
    if len(set(issues)) != len(issues):
        raise ValueError("Serving v5 narrative issues must be unique")
    orders = [highlight.sourceOrder for highlight in value.officialHighlights]
    if orders != list(range(1, len(orders) + 1)):
        raise ValueError("Serving v5 official highlight order is invalid")
    official_ready = mode in {"official_zh", "official_translated"}
    if official_ready and (
        value.officialTaglineZh is None
        or not value.officialTaglineEvidenceRefs
        or value.officialPositioningZh is None
        or not value.officialPositioningEvidenceRefs
        or not value.officialHighlights
    ):
        raise ValueError("Serving v5 official narrative is incomplete")
    if mode == "official_zh" and any(
        highlight.sourceTitle != highlight.titleZh or highlight.sourceDetail != highlight.detailZh
        for highlight in value.officialHighlights
    ):
        raise ValueError("Serving v5 Chinese official highlights must preserve author text")
    if mode == "insufficient" and (
        value.officialTaglineZh is not None
        or value.officialPositioningZh is not None
        or value.officialHighlights
        or value.rardarAssessmentZh is not None
        or value.rardarDifferentiators
    ):
        raise ValueError("Serving v5 insufficient profile must expose safe facts only")
    if value.officialTaglineZh is not None and value.identitySummaryZh != value.officialTaglineZh:
        raise ValueError("Serving v5 identity compatibility projection is invalid")
    if value.coreValueZh != value.rardarAssessmentZh:
        raise ValueError("Serving v5 assessment compatibility projection is invalid")
    if value.coreValueEvidenceRefs != value.rardarAssessmentEvidenceRefs:
        raise ValueError("Serving v5 assessment evidence projection is invalid")
    if value.keyDifferentiators != value.rardarDifferentiators:
        raise ValueError("Serving v5 differentiator compatibility projection is invalid")


def _validate_v6_positioning(value: TodayProject | OfficialProjectProfile) -> None:
    mode = value.positioningSourceMode
    if mode is None:
        raise ValueError("Serving v6 requires a field-level positioning source mode")
    if len(set(value.positioningEvidenceRefs)) != len(value.positioningEvidenceRefs):
        raise ValueError("Serving v6 positioning evidence refs must be unique")
    if len(set(value.positioningIncludedRoles)) != len(value.positioningIncludedRoles):
        raise ValueError("Serving v6 positioning roles must be unique")
    if mode == "insufficient":
        if (
            value.positioningZh is not None
            or value.positioningEvidenceRefs
            or value.positioningIncludedRoles
            or value.positioningExcludedClauses
        ):
            raise ValueError("Serving v6 insufficient positioning must expose no claims")
    else:
        if value.positioningZh is None or not value.positioningEvidenceRefs or not value.positioningIncludedRoles:
            raise ValueError("Serving v6 positioning requires text, evidence, and semantic roles")
        if not {"core_mechanism", "primary_outcome"}.intersection(value.positioningIncludedRoles):
            raise ValueError("Serving v6 positioning requires a mechanism or primary outcome")
        if value.identitySummaryZh and _primary_texts_duplicate(value.identitySummaryZh, value.positioningZh):
            raise ValueError("Serving v6 positioning must not repeat the identity summary")
    if value.officialPositioningZh != value.positioningZh:
        raise ValueError("Serving v6 legacy positioning text projection is inconsistent")
    if value.officialPositioningEvidenceRefs != value.positioningEvidenceRefs:
        raise ValueError("Serving v6 legacy positioning evidence projection is inconsistent")
