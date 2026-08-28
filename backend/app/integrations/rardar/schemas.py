"""Strict TopicEye DTOs for the Rardar explosion artifact integration."""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ExplosionWindow(StrictModel):
    state: Literal["exact", "warming_up", "baseline_missing"]
    startedAt: AwareDatetime
    endedAt: AwareDatetime
    durationHours: Literal[24]
    toleranceSeconds: Literal[600]


class ExplosionCoverage(StrictModel):
    state: Literal["healthy", "degraded"]
    successfulQueryCount: int = Field(ge=1, le=9)
    failedQueryCount: int = Field(ge=0, le=8)
    metadataFailureCount: int = Field(ge=0, le=500)
    exactCount: int = Field(ge=0, le=500)
    pendingCount: int = Field(ge=0, le=500)
    conflictCount: int = Field(ge=0, le=500)


class ExplosionSourceStatus(StrictModel):
    currentCaptureId: str
    baselineCaptureId: str | None
    partialCaptureCount: int = Field(ge=0, le=11)
    coverageWitnessCaptureId: str | None


class ExactExplosionProject(StrictModel):
    rank: int = Field(ge=1, le=500)
    githubRepositoryId: int = Field(gt=0)
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    htmlUrl: HttpUrl
    totalStars: int = Field(ge=0)
    baselineStars: int = Field(ge=0)
    observedStarDelta: int = Field(ge=0)
    windowStartedAt: AwareDatetime
    windowEndedAt: AwareDatetime
    primaryLanguage: str | None
    topics: list[str] = Field(max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    forks: int = Field(default=0, ge=0)
    pushedAt: AwareDatetime | None = None
    defaultBranch: str = Field(default="main", min_length=1, max_length=255)
    licenseSpdxId: str | None = Field(default=None, max_length=100)
    archived: bool
    fork: bool
    mirrorUrl: str | None
    state: Literal["exact_window"]


class PendingExplosionProject(StrictModel):
    pendingRank: int = Field(ge=1, le=500)
    pendingReason: Literal["first_seen", "baseline_missing", "baseline_ineligible"]
    githubRepositoryId: int = Field(gt=0)
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    htmlUrl: HttpUrl
    totalStars: int = Field(ge=0)
    firstSeenAt: AwareDatetime
    observedWindowHours: float | None = Field(default=None, ge=0, le=24)
    observedWindowStarDelta: int | None
    observedWindowStartedAt: AwareDatetime | None = None
    observedWindowEndedAt: AwareDatetime | None = None
    primaryLanguage: str | None
    topics: list[str] = Field(max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    forks: int = Field(default=0, ge=0)
    pushedAt: AwareDatetime | None = None
    defaultBranch: str = Field(default="main", min_length=1, max_length=255)
    licenseSpdxId: str | None = Field(default=None, max_length=100)


class ExplosionBoardResponse(StrictModel):
    state: Literal["ready", "warming_up", "baseline_missing", "not_ready", "not_synced"]
    reason: Literal["explosion_artifact_not_published", "real_data_not_synced"] | None = None
    generationId: str | None = None
    publishedAt: AwareDatetime | None = None
    capturedAt: AwareDatetime | None = None
    window: ExplosionWindow | None = None
    coverage: ExplosionCoverage | None = None
    exactRanked: list[ExactExplosionProject] = Field(default_factory=list, max_length=500)
    pendingRanked: list[PendingExplosionProject] = Field(default_factory=list, max_length=500)
    conflictCount: int = Field(default=0, ge=0, le=500)
    sourceStatus: ExplosionSourceStatus | None = None
    dataMode: Literal["real", "demo"] = "real"
    dataLabel: str = "Rardar 生产快照"
    syncedAt: AwareDatetime | None = None
    sourceHost: str | None = Field(default=None, max_length=100)
    manifestSha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    artifactSha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_state_payload(self) -> ExplosionBoardResponse:
        if self.state == "not_synced":
            if self.reason != "real_data_not_synced" or self.dataMode != "real":
                raise ValueError("not_synced response requires the explicit real-data reason")
            if any(
                (
                    self.generationId,
                    self.publishedAt,
                    self.capturedAt,
                    self.window,
                    self.coverage,
                    self.sourceStatus,
                    self.syncedAt,
                )
            ):
                raise ValueError("not_synced response cannot expose fabricated publication metadata")
            return self
        if self.state == "not_ready":
            if self.reason != "explosion_artifact_not_published":
                raise ValueError("not_ready response requires the stable publication reason")
            if self.generationId is None or self.publishedAt is None:
                raise ValueError("not_ready response requires a verified generation")
            if any((self.capturedAt, self.window, self.coverage, self.sourceStatus)):
                raise ValueError("not_ready response cannot expose an unvalidated artifact")
            return self
        if self.generationId is None or self.publishedAt is None:
            raise ValueError("published response requires generation metadata")
        if self.reason is not None or any(
            value is None for value in (self.capturedAt, self.window, self.coverage, self.sourceStatus)
        ):
            raise ValueError("published response requires validated artifact metadata")
        if self.state == "ready" and self.window and self.window.state != "exact":
            raise ValueError("ready response must bind to an exact observation window")
        return self
