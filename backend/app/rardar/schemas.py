"""Strict contracts for the isolated Rardar vertical slices."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class EvidenceRef(StrictModel):
    kind: Literal["github_metadata", "github_trending", "release", "repository_file", "poc_fixture"]
    label: str = Field(min_length=1, max_length=120)
    url: HttpUrl | None = None
    observedAt: AwareDatetime


class ExplosionProject(StrictModel):
    rank: int = Field(ge=1, le=20)
    projectId: str = Field(pattern=r"^p_[a-z0-9]{12}$")
    githubRepositoryId: int = Field(gt=0)
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    summaryZh: str = Field(min_length=8, max_length=240)
    coreCapabilities: list[str] = Field(min_length=2, max_length=8)
    aiStatus: Literal["pending", "ready", "failed"]
    observedStarDelta: int = Field(ge=0)
    totalStars: int = Field(ge=0)
    forks: int = Field(ge=0)
    pushedAt: AwareDatetime
    windowStartedAt: AwareDatetime
    windowEndedAt: AwareDatetime
    observationWindowHours: Literal[24]
    sourceProvenance: list[EvidenceRef] = Field(min_length=1)


class FirstSeenProject(StrictModel):
    projectId: str = Field(pattern=r"^p_[a-z0-9]{12}$")
    githubRepositoryId: int = Field(gt=0)
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    summaryZh: str = Field(min_length=8, max_length=240)
    firstSeenAt: AwareDatetime
    observedWindowHours: float = Field(gt=0, lt=24)
    observedWindowStarDelta: int = Field(ge=0)
    totalStars: int = Field(ge=0)
    externalSignals: list[str] = Field(min_length=1)
    aiStatus: Literal["pending", "ready", "failed"]
    sourceProvenance: list[EvidenceRef] = Field(min_length=1)


class CoverageStatus(StrictModel):
    candidateSources: list[str] = Field(min_length=1)
    successfulQueries: int = Field(ge=0)
    recalledCandidates: int = Field(ge=0)
    observedRepositories: int = Field(ge=0)
    degradedSources: list[str]
    statement: str = Field(min_length=12)


class ExplosionBoardArtifact(StrictModel):
    schemaVersion: Literal[1]
    generationId: str = Field(pattern=r"^poc-generation-[a-z0-9-]+$")
    artifactVersion: Literal[1]
    artifactRevision: str = Field(pattern=r"^explosion-poc-[a-z0-9-]+$")
    capturedAt: AwareDatetime
    publishedAt: AwareDatetime
    windowStartedAt: AwareDatetime
    windowEndedAt: AwareDatetime
    exactTop: list[ExplosionProject] = Field(min_length=5, max_length=20)
    firstSeenPending: list[FirstSeenProject]
    coverageState: Literal["healthy", "degraded"]
    sourceSummary: str = Field(min_length=12)
    coverage: CoverageStatus

    @model_validator(mode="after")
    def validate_rank_contract(self) -> ExplosionBoardArtifact:
        expected_ranks = list(range(1, len(self.exactTop) + 1))
        if [item.rank for item in self.exactTop] != expected_ranks:
            raise ValueError("exactTop ranks must be contiguous and authoritative")
        expected_order = sorted(
            self.exactTop,
            key=lambda item: (-item.observedStarDelta, -item.totalStars, item.repository.lower()),
        )
        if self.exactTop != expected_order:
            raise ValueError("exactTop must use observedStarDelta, totalStars, repository ordering")
        if self.windowStartedAt >= self.windowEndedAt:
            raise ValueError("observation window must move forward")
        if any(
            item.windowStartedAt != self.windowStartedAt or item.windowEndedAt != self.windowEndedAt
            for item in self.exactTop
        ):
            raise ValueError("each exact project must bind to the artifact observation window")
        if self.capturedAt < self.windowEndedAt:
            raise ValueError("capturedAt cannot precede the observation window")
        return self


class ArtifactPointer(StrictModel):
    schemaVersion: Literal[1]
    artifactRevision: str = Field(pattern=r"^explosion-poc-[a-z0-9-]+$")
    artifact: str = Field(pattern=r"^revisions/[A-Za-z0-9._-]+\.json$")
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class AIResultState(StrEnum):
    READY = "ready"
    CACHE_HIT = "cache_hit"
    FAILED = "failed"
    INVALID_JSON = "invalid_json"
    SCHEMA_MISMATCH = "schema_mismatch"
    CIRCUIT_OPEN = "circuit_open"


class AIProjectProfile(StrictModel):
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    projectId: str = Field(pattern=r"^p_[a-z0-9]{12}$")
    summaryZh: str = Field(min_length=8, max_length=240)
    coreCapabilities: list[str] = Field(min_length=2, max_length=8)
    projectForm: str = Field(min_length=3, max_length=120)
    notablePoint: str = Field(min_length=8, max_length=240)
    whyTrendingHypothesis: str = Field(min_length=12, max_length=500)
    evidenceRefs: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    limitations: list[str] = Field(min_length=1)
    sourceRevision: str = Field(min_length=3)
    model: Literal["gpt-5.6-sol"]
    reasoningEffort: Literal["medium", "high", "xhigh"]
    promptVersion: Literal["rardar-project-profile-v1"]
    schemaVersion: Literal[1]
    generatedAt: AwareDatetime


class ProviderTrace(StrictModel):
    requestId: str = Field(pattern=r"^mock_req_[a-f0-9]{16}_[0-9]+_[a-f0-9]{32}$")
    provider: Literal["mock_sub2api"]
    model: Literal["gpt-5.6-sol"]
    reasoningEffort: Literal["medium", "high", "xhigh"]
    inputTokens: int = Field(ge=0)
    cachedTokens: int = Field(ge=0)
    outputTokens: int = Field(ge=0)
    attemptCount: int = Field(ge=1)


class AIEnvelope(StrictModel):
    result: dict
    providerTrace: ProviderTrace


class RequirementProfile(StrictModel):
    goal: str = Field(min_length=6, max_length=400)
    mustHave: list[str] = Field(min_length=1, max_length=10)
    niceToHave: list[str] = Field(max_length=10)
    constraints: list[str] = Field(max_length=10)
    exclude: list[str] = Field(max_length=10)
    technologyStack: list[str] = Field(max_length=10)
    deployment: list[str] = Field(min_length=1, max_length=10)
    licensePreference: list[str] = Field(max_length=10)
    reuseGranularity: list[str] = Field(min_length=1, max_length=10)
    acceptanceCriteria: list[str] = Field(min_length=1, max_length=10)
    repositoryContext: str | None = Field(default=None, max_length=200)


class CandidateEvidence(StrictModel):
    label: str
    kind: Literal["readme", "repository", "release", "license", "poc_fixture"]
    url: HttpUrl


class FindCandidate(StrictModel):
    projectId: str = Field(pattern=r"^p_[a-z0-9]{12}$")
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    summaryZh: str
    capabilities: list[str] = Field(min_length=2)
    technicalTags: list[str]
    license: str
    engineeringEvidence: list[CandidateEvidence] = Field(min_length=1)


class CandidateFixture(StrictModel):
    schemaVersion: Literal[1]
    fixtureRevision: str = Field(pattern=r"^find-candidates-poc-[a-z0-9-]+$")
    capturedAt: AwareDatetime
    candidates: list[FindCandidate] = Field(min_length=5)


class MatchedProject(StrictModel):
    projectId: str = Field(pattern=r"^p_[a-z0-9]{12}$")
    repository: str
    summaryZh: str
    whyMatched: str
    mustHaveCoverage: list[str]
    missingCapabilities: list[str]
    unknownCapabilities: list[str]
    technicalCompatibility: str
    reuseType: Literal[
        "whole_product",
        "module_or_library",
        "provider_or_connector",
        "workflow",
        "reference_only",
        "not_recommended",
    ]
    referenceKinds: list[Literal["architecture", "ui", "workflow_design", "knowledge", "infrastructure"]]
    integrationCost: Literal["low", "medium", "high"]
    integrationWorkItems: list[str]
    engineeringEvidence: list[CandidateEvidence]
    licenseAndRisk: str
    evidenceRefs: list[str]
    confidence: float = Field(ge=0, le=1)
    nextValidationAction: str


class FindProjectResult(StrictModel):
    requirementProfile: RequirementProfile
    candidates: list[MatchedProject] = Field(min_length=3, max_length=3)
    comparedAt: AwareDatetime
    sourceRevision: str
    model: Literal["gpt-5.6-sol"]
    reasoningEffort: Literal["xhigh"]


class FindProjectCreate(StrictModel):
    query: str = Field(min_length=6, max_length=800)
    repositoryUrl: HttpUrl | None = None
    scenario: Literal[
        "success",
        "job_fail_once",
        "timeout",
        "429",
        "5xx",
        "invalid_json",
        "schema_mismatch",
    ] = "success"


class FindProjectConfirm(StrictModel):
    requirementProfile: RequirementProfile


def utc_now() -> datetime:
    from datetime import UTC

    return datetime.now(UTC)
