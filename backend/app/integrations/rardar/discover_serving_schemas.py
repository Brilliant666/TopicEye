"""Immutable TopicEye Serving contracts for Rardar Discover."""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.integrations.rardar.discover import (
    DiscoverCoverage,
    DiscoverItem,
    DiscoverStageCounts,
    DiscoverSuppressionSummary,
)
from app.integrations.rardar.serving_schemas import (
    OfficialProjectProfile,
    ProjectEvidenceProjection,
    ServingCapability,
)


class StrictDiscoverServingModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class DiscoverServingCard(DiscoverItem):
    identitySummaryZh: str = Field(min_length=2, max_length=300)
    positioningZh: str = Field(min_length=2, max_length=1200)
    capabilities: list[ServingCapability] = Field(min_length=1, max_length=6)
    sourceMode: Literal["official_zh", "official_translated", "rardar_derived"]
    qualityState: Literal["ready", "partial"]
    category: Literal["ai-agent", "dev-tools", "data-infra", "productivity", "video-content", "other"] | None = None
    categorySourceMode: Literal["canonical_profile", "github_metadata", "deterministic_fallback"] | None = None
    categoryEvidenceRefs: list[str] = Field(default_factory=list, max_length=8)


class DiscoverProfileSummary(StrictDiscoverServingModel):
    selectedCount: int = Field(ge=0, le=30)
    identityComplete: int = Field(ge=0, le=30)
    positioningComplete: int = Field(ge=0, le=30)
    capabilitiesComplete: int = Field(ge=0, le=30)
    categoryComplete: int = Field(default=0, ge=0, le=30)
    officialZh: int = Field(ge=0, le=30)
    officialTranslated: int = Field(ge=0, le=30)
    rardarDerived: int = Field(ge=0, le=30)
    githubRequests: int = Field(ge=0)
    readmeCacheHits: int = Field(ge=0)
    translationCalls: int = Field(ge=0)
    translationCacheHits: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> DiscoverProfileSummary:
        if not (self.identityComplete == self.positioningComplete == self.capabilitiesComplete == self.selectedCount):
            raise ValueError("every selected Discover profile must be complete")
        if self.categoryComplete not in {0, self.selectedCount}:
            raise ValueError("Discover categories must cover either none or every selected project")
        if self.officialZh + self.officialTranslated + self.rardarDerived != self.selectedCount:
            raise ValueError("Discover profile source modes do not cover the selected set")
        return self


class DiscoverServingSnapshot(StrictDiscoverServingModel):
    schemaVersion: Literal[1, 2]
    servingGenerationId: str = Field(min_length=1, max_length=128)
    discoverGenerationId: str = Field(min_length=1, max_length=128)
    generatedAt: AwareDatetime
    latestCaptureId: str
    latestCaptureAt: AwareDatetime
    nextExpectedAt: AwareDatetime
    updateCadenceMinutes: Literal[120]
    stageCounts: DiscoverStageCounts
    justDiscovered: list[DiscoverServingCard] = Field(max_length=10)
    rising: list[DiscoverServingCard] = Field(max_length=10)
    nearValidation: list[DiscoverServingCard] = Field(max_length=10)
    coverage: DiscoverCoverage
    conflictCount: int = Field(ge=0, le=500)
    conflictReasons: dict[str, int]
    todayExplosionGenerationId: str
    sourceWindowStart: AwareDatetime
    sourceWindowEnd: AwareDatetime
    sourceCaptureCount: int = Field(ge=1, le=14)
    sourceManifestSha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    sourceArtifactSha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    syncedAt: AwareDatetime | None
    sourceHost: str | None = Field(default=None, max_length=100)
    profileSummary: DiscoverProfileSummary
    sourceSchemaVersion: Literal[1, 2] | None = None
    sourcePolicyVersion: Literal["trending-discover-v1", "trending-discover-v2"] | None = None
    suppressionSummary: DiscoverSuppressionSummary | None = None

    @model_validator(mode="after")
    def validate_projection(self) -> DiscoverServingSnapshot:
        groups = (
            ("just_discovered", self.justDiscovered),
            ("rising", self.rising),
            ("near_validation", self.nearValidation),
        )
        identifiers: list[int] = []
        for expected, values in groups:
            if any(item.stage != expected for item in values):
                raise ValueError("Discover Serving stage partition is invalid")
            identifiers.extend(item.githubRepositoryId for item in values)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Discover Serving project identity is duplicated")
        if self.profileSummary.selectedCount != len(identifiers):
            raise ValueError("Discover Serving profile inventory is incomplete")
        if self.schemaVersion == 2:
            if (
                self.profileSummary.categoryComplete != len(identifiers)
                or self.sourceSchemaVersion is None
                or self.sourcePolicyVersion is None
                or (self.sourceSchemaVersion == 2) != (self.suppressionSummary is not None)
            ):
                raise ValueError("Discover Serving v2 policy projection is incomplete")
            if any(
                item.category is None or item.categorySourceMode is None or not item.categoryEvidenceRefs
                for _, values in groups
                for item in values
            ):
                raise ValueError("Discover Serving v2 category projection is incomplete")
        if self.stageCounts.justDiscovered < len(self.justDiscovered):
            raise ValueError("Discover Serving just-discovered count exceeds source")
        if self.stageCounts.rising < len(self.rising):
            raise ValueError("Discover Serving rising count exceeds source")
        if self.stageCounts.nearValidation < len(self.nearValidation):
            raise ValueError("Discover Serving near-validation count exceeds source")
        return self


class DiscoverServingProjectRecord(StrictDiscoverServingModel):
    schemaVersion: Literal[1, 2]
    servingGenerationId: str
    discoverGenerationId: str
    facts: DiscoverItem
    profile: OfficialProjectProfile
    category: Literal["ai-agent", "dev-tools", "data-infra", "productivity", "video-content", "other"] | None = None
    categorySourceMode: Literal["canonical_profile", "github_metadata", "deterministic_fallback"] | None = None
    categoryEvidenceRefs: list[str] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def validate_identity(self) -> DiscoverServingProjectRecord:
        if (
            self.facts.githubRepositoryId != self.profile.githubRepositoryId
            or self.facts.repository != self.profile.repository
            or self.discoverGenerationId != self.profile.generationId
        ):
            raise ValueError("Discover project/profile identity is inconsistent")
        if self.schemaVersion == 2 and (
            self.category is None or self.categorySourceMode is None or not self.categoryEvidenceRefs
        ):
            raise ValueError("Discover project category is incomplete")
        return self


class DiscoverProjectDetail(StrictDiscoverServingModel):
    schemaVersion: Literal[1, 2]
    servingGenerationId: str
    discoverGenerationId: str
    facts: DiscoverItem
    profile: OfficialProjectProfile
    evidence: ProjectEvidenceProjection
    coverage: DiscoverCoverage
    conflictCount: int = Field(ge=0, le=500)
    category: Literal["ai-agent", "dev-tools", "data-infra", "productivity", "video-content", "other"] | None = None
    categorySourceMode: Literal["canonical_profile", "github_metadata", "deterministic_fallback"] | None = None
    categoryEvidenceRefs: list[str] = Field(default_factory=list, max_length=8)
    nextExpectedAt: AwareDatetime | None = None
    nextTodaySettlementAt: AwareDatetime | None = None
    todayStatus: Literal["not_in_source_today"] | None = None
    todayReason: Literal["new_candidate", "awaiting_growth_evidence", "awaiting_daily_settlement"] | None = None

    @model_validator(mode="after")
    def validate_identity(self) -> DiscoverProjectDetail:
        identifier = self.facts.githubRepositoryId
        if (
            self.profile.githubRepositoryId != identifier
            or self.evidence.githubRepositoryId != identifier
            or self.profile.repository != self.facts.repository
            or self.evidence.repository != self.facts.repository
            or self.profile.generationId != self.discoverGenerationId
            or self.evidence.generationId != self.discoverGenerationId
        ):
            raise ValueError("Discover detail identity is inconsistent")
        if self.schemaVersion == 2 and (
            self.category is None
            or self.categorySourceMode is None
            or not self.categoryEvidenceRefs
            or self.nextExpectedAt is None
            or self.nextTodaySettlementAt is None
            or self.todayStatus is None
            or self.todayReason is None
        ):
            raise ValueError("Discover detail v2 context is incomplete")
        return self


class DiscoverServingPointer(StrictDiscoverServingModel):
    schemaVersion: Literal[1, 2]
    generationId: str = Field(min_length=1, max_length=128)
    discoverGenerationId: str = Field(min_length=1, max_length=128)
    publishedAt: AwareDatetime
    previousGenerationId: str | None = Field(default=None, max_length=128)
    manifestSha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class DiscoverServingFile(StrictDiscoverServingModel):
    path: str = Field(pattern=r"^(?:discover\.json|projects/[1-9][0-9]*\.json|evidence/[1-9][0-9]*\.json)$")
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    bytes: int = Field(gt=0, le=16 * 1024 * 1024)


class DiscoverServingManifest(StrictDiscoverServingModel):
    schemaVersion: Literal[1, 2]
    generationId: str
    discoverGenerationId: str
    createdAt: AwareDatetime
    state: Literal["ready"]
    sourceManifestSha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    sourceArtifactSha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    files: list[DiscoverServingFile] = Field(min_length=1, max_length=61)
    projectIds: list[int] = Field(max_length=30)
    profileSummary: DiscoverProfileSummary

    @model_validator(mode="after")
    def validate_inventory(self) -> DiscoverServingManifest:
        paths = [item.path for item in self.files]
        if len(paths) != len(set(paths)) or "discover.json" not in paths:
            raise ValueError("Discover Serving file inventory is invalid")
        if len(self.projectIds) != len(set(self.projectIds)):
            raise ValueError("Discover Serving project inventory is duplicated")
        expected = {"discover.json"}
        expected.update(f"projects/{value}.json" for value in self.projectIds)
        expected.update(f"evidence/{value}.json" for value in self.projectIds)
        if set(paths) != expected or len(self.projectIds) != self.profileSummary.selectedCount:
            raise ValueError("Discover Serving manifest is incomplete")
        return self


class DiscoverServingStages(StrictDiscoverServingModel):
    justDiscovered: list[DiscoverServingCard] = Field(max_length=10)
    rising: list[DiscoverServingCard] = Field(max_length=10)
    nearValidation: list[DiscoverServingCard] = Field(max_length=10)


class DiscoverConflictSummary(StrictDiscoverServingModel):
    count: int = Field(ge=0, le=500)
    reasons: dict[str, int] = Field(max_length=32)


class DiscoverApiResponse(StrictDiscoverServingModel):
    status: Literal["ready", "empty", "stale", "not_configured", "invalid"]
    generation: str | None = None
    generatedAt: AwareDatetime | None = None
    latestCaptureId: str | None = None
    latestCaptureAt: AwareDatetime | None = None
    nextExpectedAt: AwareDatetime | None = None
    freshnessState: Literal["fresh", "stale", "unavailable"]
    updateCadenceMinutes: Literal[120]
    stageCounts: DiscoverStageCounts
    stages: DiscoverServingStages
    coverage: DiscoverCoverage | None = None
    conflicts: DiscoverConflictSummary
    todayExplosionGenerationId: str | None = None
    sourceWindowStart: AwareDatetime | None = None
    sourceWindowEnd: AwareDatetime | None = None
    sourceCaptureCount: int = Field(default=0, ge=0, le=14)
    profileSummary: DiscoverProfileSummary | None = None
    sourceSchemaVersion: Literal[1, 2] | None = None
    sourcePolicyVersion: Literal["trending-discover-v1", "trending-discover-v2"] | None = None
    suppressionSummary: DiscoverSuppressionSummary | None = None
    code: str | None = Field(default=None, max_length=100)


__all__ = [
    "DiscoverApiResponse",
    "DiscoverProfileSummary",
    "DiscoverConflictSummary",
    "DiscoverProjectDetail",
    "DiscoverServingCard",
    "DiscoverServingFile",
    "DiscoverServingManifest",
    "DiscoverServingPointer",
    "DiscoverServingProjectRecord",
    "DiscoverServingSnapshot",
    "DiscoverServingStages",
]
