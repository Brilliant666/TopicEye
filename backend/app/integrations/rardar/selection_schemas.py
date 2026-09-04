"""Strict contracts for the local-shadow Rardar worth-seeing selection."""

from __future__ import annotations

import math
import re
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, model_validator


class StrictSelectionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


ScopeStatus = Literal["in_scope", "out_of_scope", "uncertain"]
ValueVerdict = Literal["strong", "moderate", "weak", "uncertain"]
Confidence = Literal["high", "medium", "low"]
PrimaryReason = Literal[
    "directly_reusable",
    "specific_problem_solution",
    "distinctive_implementation",
    "reference_or_learning_value",
]
TimelinessVerdict = Literal["strong", "weak", "none", "uncertain"]
SemanticDecision = Literal["SELECT_NOW", "WORTHWHILE_NOT_NOW", "REJECT", "UNCERTAIN"]
PublicationDisposition = Literal[
    "publish",
    "hold",
    "suppress_duplicate",
    "suppress_capacity",
    "not_eligible",
]
SelectionCategory = Literal["ai-agent", "dev-tools", "data-infra", "productivity", "video-content", "other"]

_RETRYABLE_PROFILE_FAILURES = {
    "profile_source_timeout",
    "profile_source_rate_limited",
    "profile_source_http_5xx",
    "profile_source_remote_disconnected",
    "profile_source_http_404",
    "profile_translation_unavailable",
    "profile_model_unavailable",
    "profile_model_invalid_output",
    "profile_build_interrupted",
    "profile_unknown_failure",
}
_PERMANENT_PROFILE_FAILURES = {
    "profile_source_invalid",
    "profile_evidence_incomplete",
    "profile_evidence_mismatch",
    "profile_schema_invalid",
    "profile_path_unsafe",
}


class SelectionEvidenceAlias(StrictSelectionModel):
    evidenceId: str = Field(pattern=r"^[ETP][0-9]{2}$")
    sourceType: Literal["description", "profile", "readme", "tree", "release", "revision", "peer"]
    sourcePath: str = Field(min_length=1, max_length=500)
    sourceRevision: str = Field(min_length=1, max_length=200)
    excerpt: str = Field(min_length=1, max_length=1600)
    githubRepositoryId: int = Field(gt=0)


class SelectionReasonCandidate(StrictSelectionModel):
    reason: PrimaryReason
    supported: bool
    evidenceIds: list[str] = Field(max_length=12)

    @model_validator(mode="after")
    def validate_support(self) -> SelectionReasonCandidate:
        if len(self.evidenceIds) != len(set(self.evidenceIds)):
            raise ValueError("reason evidenceIds must be unique")
        if self.supported and not self.evidenceIds:
            raise ValueError("supported reasons require evidence")
        return self


class SelectionGateResult(StrictSelectionModel):
    scopeStatus: ScopeStatus
    valueVerdict: ValueVerdict
    reasonCandidates: list[SelectionReasonCandidate] = Field(max_length=4)
    counterEvidenceIds: list[str] = Field(max_length=12)
    confidence: Confidence

    @model_validator(mode="after")
    def unique_values(self) -> SelectionGateResult:
        reasons = [item.reason for item in self.reasonCandidates]
        if len(reasons) != len(set(reasons)):
            raise ValueError("reasonCandidates must be unique")
        if len(self.counterEvidenceIds) != len(set(self.counterEvidenceIds)):
            raise ValueError("counterEvidenceIds must be unique")
        identifiers = [identifier for item in self.reasonCandidates for identifier in item.evidenceIds]
        if any(not re.fullmatch(r"E[0-9]{2}", identifier) for identifier in identifiers + self.counterEvidenceIds):
            raise ValueError("value gate may reference only E aliases")
        return self


class MeaningfulChangeResult(StrictSelectionModel):
    meaningfulRelease: Literal["yes", "no", "uncertain"]
    meaningfulUpdate: Literal["yes", "no", "uncertain"]
    evidenceIds: list[str] = Field(max_length=8)
    confidence: Confidence

    @model_validator(mode="after")
    def validate_aliases(self) -> MeaningfulChangeResult:
        if len(self.evidenceIds) != len(set(self.evidenceIds)) or any(
            not re.fullmatch(r"T[0-9]{2}", identifier) for identifier in self.evidenceIds
        ):
            raise ValueError("meaningful change may reference only unique T aliases")
        return self


class SelectionTimeliness(StrictSelectionModel):
    verdict: TimelinessVerdict
    confidence: Confidence
    reasonCodes: list[
        Literal[
            "genuinely_new_asset",
            "meaningful_release",
            "meaningful_update",
            "strong_recent_momentum",
            "no_strong_why_now",
            "evidence_uncertain",
        ]
    ] = Field(min_length=1, max_length=6)
    evidenceIds: list[str] = Field(max_length=12)
    meaningfulChange: MeaningfulChangeResult | None = None
    strongSignals: list[
        Literal[
            "genuinely_new_asset",
            "meaningful_release",
            "meaningful_update",
            "strong_recent_momentum",
        ]
    ] = Field(max_length=4)
    weakSignals: list[
        Literal[
            "newly_observed",
            "recent_activity",
            "awaiting_today_validation",
        ]
    ] = Field(max_length=3)

    @model_validator(mode="after")
    def validate_signals(self) -> SelectionTimeliness:
        if (
            len(self.reasonCodes) != len(set(self.reasonCodes))
            or len(self.evidenceIds) != len(set(self.evidenceIds))
            or len(self.strongSignals) != len(set(self.strongSignals))
            or len(self.weakSignals) != len(set(self.weakSignals))
            or any(not re.fullmatch(r"T[0-9]{2}", identifier) for identifier in self.evidenceIds)
        ):
            raise ValueError("timeliness signals or aliases are invalid")
        return self


class SelectionCopyResult(StrictSelectionModel):
    identitySummaryZh: str = Field(min_length=4, max_length=180)
    whyWorthSeeingZh: str = Field(min_length=8, max_length=360)
    whyNowZh: str | None = Field(default=None, min_length=4, max_length=240)
    reusableAssets: list[str] = Field(max_length=3)
    bestFit: list[str] = Field(max_length=3)
    evidenceIds: list[str] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def unique_evidence(self) -> SelectionCopyResult:
        if len(self.evidenceIds) != len(set(self.evidenceIds)):
            raise ValueError("copy evidenceIds must be unique")
        if any(not value.strip() or len(value) > 160 for value in self.reusableAssets + self.bestFit):
            raise ValueError("copy list values are invalid")
        if any(not re.fullmatch(r"[ET][0-9]{2}", identifier) for identifier in self.evidenceIds):
            raise ValueError("copy may reference only E/T aliases")
        return self


class SelectionCandidateFacts(StrictSelectionModel):
    githubRepositoryId: int = Field(gt=0)
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    htmlUrl: HttpUrl
    description: str | None = Field(default=None, max_length=2000)
    primaryLanguage: str | None = Field(default=None, max_length=100)
    topics: list[str] = Field(max_length=100)
    licenseSpdxId: str | None = Field(default=None, max_length=100)
    totalStars: int = Field(ge=0)
    forks: int = Field(ge=0)
    createdAt: AwareDatetime
    updatedAt: AwareDatetime
    pushedAt: AwareDatetime
    archived: Literal[False]
    disabled: Literal[False]
    fork: Literal[False]
    defaultBranch: str = Field(min_length=1, max_length=250)
    todayExactRank: int | None = Field(default=None, ge=21)
    observedStarDelta: int | None = None
    observedWindowHours: float | None = Field(default=None, ge=0, le=72)
    firstObservedAt: AwareDatetime
    lastObservedAt: AwareDatetime
    observationCount: int = Field(ge=1, le=64)
    recallChannels: list[
        Literal[
            "reusable_asset",
            "specific_problem",
            "genuinely_new",
            "meaningful_change",
            "reference_learning",
            "momentum",
        ]
    ] = Field(max_length=6)

    @model_validator(mode="after")
    def validate_identity(self) -> SelectionCandidateFacts:
        if len(self.recallChannels) != len(set(self.recallChannels)):
            raise ValueError("recall channels must be unique")
        url = self.htmlUrl
        if (
            url.scheme != "https"
            or url.host != "github.com"
            or url.username is not None
            or url.password is not None
            or url.query is not None
            or url.fragment is not None
            or url.path.rstrip("/") != f"/{self.repository}"
        ):
            raise ValueError("candidate GitHub URL is not canonical")
        return self


class SelectionAssessment(StrictSelectionModel):
    candidate: SelectionCandidateFacts
    selectionEvidenceDigest: str = Field(pattern=r"^[a-f0-9]{64}$")
    peerContextDigest: str = Field(pattern=r"^[a-f0-9]{64}$")
    valueEvidence: list[SelectionEvidenceAlias] = Field(max_length=32)
    timelinessEvidence: list[SelectionEvidenceAlias] = Field(max_length=16)
    peerEvidence: list[SelectionEvidenceAlias] = Field(max_length=8)
    gate: SelectionGateResult | None
    timeliness: SelectionTimeliness
    semanticDecision: SemanticDecision
    primaryReason: PrimaryReason | None
    supportingReasons: list[PrimaryReason] = Field(max_length=2)
    publicationDisposition: PublicationDisposition
    nearDuplicateGroup: str | None = Field(default=None, max_length=160)
    rejectReason: (
        Literal[
            "out_of_product_scope",
            "no_clear_value",
            "weak_evidence",
            "popularity_only",
            "marketing_only",
            "not_reusable_or_actionable",
            "maintenance_or_license_concern",
            "identity_or_source_invalid",
        ]
        | None
    ) = None
    failureCode: str | None = Field(default=None, max_length=80)
    gateAttempts: int = Field(ge=0, le=2)
    meaningfulChangeAttempts: int = Field(ge=0, le=2)
    copyAttempts: int = Field(ge=0, le=2)
    copyResult: SelectionCopyResult | None = None
    category: SelectionCategory
    categorySource: Literal["canonical_profile", "research_derived"]
    productFormsZh: list[str] = Field(max_length=3)
    displayOrder: int | None = Field(default=None, ge=1, le=20)

    @model_validator(mode="after")
    def validate_projection(self) -> SelectionAssessment:
        if self.semanticDecision in {"SELECT_NOW", "WORTHWHILE_NOT_NOW"} and self.primaryReason is None:
            raise ValueError("positive decisions require a primary reason")
        if self.publicationDisposition == "publish" and self.semanticDecision != "SELECT_NOW":
            raise ValueError("only SELECT_NOW may publish")
        if self.copyResult is not None and self.publicationDisposition != "publish":
            raise ValueError("user copy belongs only to published items")
        if (self.publicationDisposition == "publish") != (self.displayOrder is not None):
            raise ValueError("published items require one display order")
        aliases = self.valueEvidence + self.timelinessEvidence + self.peerEvidence
        identifiers = {item.githubRepositoryId for item in aliases}
        if identifiers and identifiers != {self.candidate.githubRepositoryId}:
            raise ValueError("cross-repository evidence is forbidden")
        evidence_ids = [item.evidenceId for item in aliases]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evidence aliases must be unique per assessment")
        if any(not item.evidenceId.startswith("E") for item in self.valueEvidence):
            raise ValueError("value evidence must use E aliases")
        if any(not item.evidenceId.startswith("T") for item in self.timelinessEvidence):
            raise ValueError("timeliness evidence must use T aliases")
        if any(not item.evidenceId.startswith("P") for item in self.peerEvidence):
            raise ValueError("peer evidence must use P aliases")
        value_ids = {item.evidenceId for item in self.valueEvidence}
        timely_ids = {item.evidenceId for item in self.timelinessEvidence}
        if self.gate is not None:
            gate_ids = {identifier for reason in self.gate.reasonCandidates for identifier in reason.evidenceIds} | set(
                self.gate.counterEvidenceIds
            )
            if not gate_ids.issubset(value_ids):
                raise ValueError("gate references unavailable evidence")
        if not set(self.timeliness.evidenceIds).issubset(timely_ids):
            raise ValueError("timeliness references unavailable evidence")
        if self.timeliness.meaningfulChange is not None and not set(
            self.timeliness.meaningfulChange.evidenceIds
        ).issubset(timely_ids):
            raise ValueError("meaningful change references unavailable evidence")
        if self.copyResult is not None and not set(self.copyResult.evidenceIds).issubset(value_ids | timely_ids):
            raise ValueError("copy references unavailable evidence")
        return self


class SelectionUsageSummary(StrictSelectionModel):
    modelCalls: int = Field(ge=0, le=120)
    gateCalls: int = Field(ge=0, le=120)
    meaningfulChangeCalls: int = Field(ge=0, le=25)
    copyCalls: int = Field(ge=0, le=20)
    retries: int = Field(ge=0, le=120)
    cacheHits: int = Field(ge=0)
    githubRequests: int = Field(ge=0)
    inputTokens: int | None = Field(default=None, ge=0)
    cachedTokens: int | None = Field(default=None, ge=0)
    outputTokens: int | None = Field(default=None, ge=0)
    latencyMs: int = Field(ge=0)
    estimatedCostUsd: float | None = Field(default=None, ge=0)


class SelectionSourceFile(StrictSelectionModel):
    path: str = Field(pattern=r"^[A-Za-z0-9._/-]+\.json$")
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    bytes: int = Field(ge=2, le=16 * 1024 * 1024)

    @model_validator(mode="after")
    def validate_path(self) -> SelectionSourceFile:
        if self.path.startswith("/") or any(part in {"", ".", ".."} for part in self.path.split("/")):
            raise ValueError("selection source path is unsafe")
        return self


class SelectionSourceManifest(StrictSelectionModel):
    schemaVersion: Literal[1]
    state: Literal["ready"]
    sourceObservationSetId: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{1,190}$")
    capturedAt: AwareDatetime
    latestCaptureId: str = Field(min_length=2, max_length=160)
    latestCaptureAt: AwareDatetime
    sourceWindowStart: AwareDatetime
    sourceWindowEnd: AwareDatetime
    sourceCoverageState: Literal["healthy", "degraded"]
    todayGenerationId: str = Field(min_length=2, max_length=127)
    todayExplosionSha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    todayPublishedSetDigest: str = Field(pattern=r"^[a-f0-9]{64}$")
    captureIds: list[str] = Field(min_length=2, max_length=40)
    files: list[SelectionSourceFile] = Field(min_length=6, max_length=80)
    inventoryDigest: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_inventory(self) -> SelectionSourceManifest:
        paths = [item.path for item in self.files]
        if len(paths) != len(set(paths)) or len(self.captureIds) != len(set(self.captureIds)):
            raise ValueError("selection source inventory contains duplicates")
        required = {"today/current.json", "today/manifest.json", "today/explosion.json"}
        required.update(f"captures/{capture_id}.json" for capture_id in self.captureIds)
        if not required.issubset(paths):
            raise ValueError("selection source inventory is incomplete")
        if self.latestCaptureId != self.captureIds[-1]:
            raise ValueError("selection source latest capture is inconsistent")
        if self.sourceWindowEnd <= self.sourceWindowStart or self.latestCaptureAt != self.sourceWindowEnd:
            raise ValueError("selection source window is inconsistent")
        return self


class SelectionSourcePointer(StrictSelectionModel):
    schemaVersion: Literal[1]
    sourceObservationSetId: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{1,190}$")
    manifestSha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    activatedAt: AwareDatetime


class SelectionArtifact(StrictSelectionModel):
    schemaVersion: Literal[1]
    policyVersion: Literal["worth-seeing-selection-v1"]
    selectionGenerationId: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{1,190}$")
    generatedAt: AwareDatetime
    sourceObservationSetId: str = Field(min_length=2, max_length=190)
    sourceManifestSha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    sourceInventorySha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    sourcePointerSha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    sourceCaptureIds: list[str] = Field(min_length=2, max_length=40)
    sourceCaptureDigests: dict[str, str] = Field(min_length=2, max_length=40)
    sourceCaptureInventoryDigest: str = Field(pattern=r"^[a-f0-9]{64}$")
    latestCaptureId: str = Field(min_length=2, max_length=160)
    latestCaptureAt: AwareDatetime
    sourceWindowStart: AwareDatetime
    sourceWindowEnd: AwareDatetime
    todayGenerationId: str = Field(min_length=2, max_length=127)
    todayExplosionSha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    todayPublishedSetDigest: str = Field(pattern=r"^[a-f0-9]{64}$")
    sourceCoverageState: Literal["healthy", "degraded"]
    candidateUniverseVersion: Literal["worth-seeing-universe-v1"]
    candidateUniverseDigest: str = Field(pattern=r"^[a-f0-9]{64}$")
    inputDigest: str = Field(pattern=r"^[a-f0-9]{64}$")
    contractVersions: dict[str, str] = Field(min_length=1, max_length=20)
    protocolMode: Literal["prompt_json_with_local_strict_validation"]
    modelRouteIdentity: str = Field(pattern=r"^[a-f0-9]{64}$")
    modelRouteIdentities: list[str] = Field(max_length=8)
    universeCount: int = Field(ge=0, le=500)
    observationCandidateCount: int = Field(ge=0, le=500)
    exactOutsideTop20Count: int = Field(ge=0, le=500)
    preExactCount: int = Field(ge=0, le=500)
    metadataIncompleteCount: int = Field(ge=0, le=500)
    recalledCount: int = Field(ge=0, le=60)
    assessedCount: int = Field(ge=0, le=60)
    publishedCount: int = Field(ge=0, le=20)
    todayExcludedCount: int = Field(ge=0, le=20)
    invalidExcludedCount: int = Field(ge=0, le=500)
    nonMomentumRecallCount: int = Field(ge=0, le=60)
    momentumOnlyRecallCount: int = Field(ge=0, le=60)
    negativeControlCount: Literal[6]
    negativeControlFailures: list[str] = Field(max_length=6)
    decisionCounts: dict[SemanticDecision, int]
    publicationCounts: dict[PublicationDisposition, int]
    failureSummary: dict[str, int]
    assessments: list[SelectionAssessment] = Field(max_length=60)
    usage: SelectionUsageSummary
    payloadDigest: str = Field(pattern=r"^[a-f0-9]{64}$")
    profileCacheIdentityVersion: Literal[1, 2] = 1
    sourceFactDigest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    profileRevisionSetDigest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    profileBindingSetDigest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    assessmentResultDigest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    failureResolutionDigest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    profileReadyCount: int | None = Field(default=None, ge=0, le=60)
    profileReboundCount: int | None = Field(default=None, ge=0, le=60)
    profileRebuiltCount: int | None = Field(default=None, ge=0, le=60)
    profileRetryableFailureCount: int | None = Field(default=None, ge=0, le=60)
    profilePermanentUnavailableCount: int | None = Field(default=None, ge=0, le=60)
    gateAssessedCount: int | None = Field(default=None, ge=0, le=60)
    semanticResolvedCount: int | None = Field(default=None, ge=0, le=60)
    unresolvedCount: int | None = Field(default=None, ge=0, le=60)
    profileCoverage: float | None = Field(default=None, ge=0, le=1)
    assessmentCoverage: float | None = Field(default=None, ge=0, le=1)
    failureHistogram: dict[str, int] | None = None
    systemicFailureCodes: list[str] | None = Field(default=None, max_length=20)
    state: Literal["ready", "empty", "degraded", "invalid"] | None = None
    currentEligible: bool | None = None
    latestAttemptGeneration: str | None = Field(default=None, max_length=190)

    @model_validator(mode="after")
    def validate_counts(self) -> SelectionArtifact:
        if len(self.sourceCaptureIds) != len(set(self.sourceCaptureIds)):
            raise ValueError("source capture IDs must be unique")
        if set(self.sourceCaptureIds) != set(self.sourceCaptureDigests):
            raise ValueError("source capture inventory is inconsistent")
        if any(not re.fullmatch(r"[a-f0-9]{64}", value) for value in self.sourceCaptureDigests.values()):
            raise ValueError("source capture digest is invalid")
        if self.assessedCount != len(self.assessments):
            raise ValueError("assessment count mismatch")
        if self.publishedCount != sum(item.publicationDisposition == "publish" for item in self.assessments):
            raise ValueError("publication count mismatch")
        if self.usage.modelCalls > 120:
            raise ValueError("model call budget exceeded")
        if sum(self.decisionCounts.values()) != self.assessedCount:
            raise ValueError("decision counts are inconsistent")
        if sum(self.publicationCounts.values()) != self.assessedCount:
            raise ValueError("publication counts are inconsistent")
        if self.usage.githubRequests > self.assessedCount * 4:
            raise ValueError("per-project GitHub request budget exceeded")
        if self.exactOutsideTop20Count + self.preExactCount != self.universeCount:
            raise ValueError("candidate universe partitions are inconsistent")
        if self.observationCandidateCount != (self.universeCount + self.todayExcludedCount + self.invalidExcludedCount):
            raise ValueError("candidate exclusion counts are inconsistent")
        if self.nonMomentumRecallCount + self.momentumOnlyRecallCount != self.recalledCount:
            raise ValueError("recall channel counts are inconsistent")
        if self.sourceWindowEnd < self.sourceWindowStart or self.latestCaptureAt != self.sourceWindowEnd:
            raise ValueError("source window is inconsistent")
        if any(len(value) > 300 for value in self.modelRouteIdentities):
            raise ValueError("model route metadata is oversized")
        orders = sorted(item.displayOrder for item in self.assessments if item.displayOrder is not None)
        if orders != list(range(1, self.publishedCount + 1)):
            raise ValueError("display orders must be contiguous")
        if self.profileCacheIdentityVersion == 2:
            required = (
                self.sourceFactDigest,
                self.profileRevisionSetDigest,
                self.profileBindingSetDigest,
                self.assessmentResultDigest,
                self.failureResolutionDigest,
                self.profileReadyCount,
                self.profileReboundCount,
                self.profileRebuiltCount,
                self.profileRetryableFailureCount,
                self.profilePermanentUnavailableCount,
                self.gateAssessedCount,
                self.semanticResolvedCount,
                self.unresolvedCount,
                self.profileCoverage,
                self.assessmentCoverage,
                self.failureHistogram,
                self.systemicFailureCodes,
                self.state,
                self.currentEligible,
                self.latestAttemptGeneration,
            )
            if any(value is None for value in required):
                raise ValueError("selection v2 activation metrics are incomplete")
            if self.latestAttemptGeneration != self.selectionGenerationId:
                raise ValueError("selection latest attempt identity is inconsistent")
            if (
                self.profileReadyCount + self.profileRetryableFailureCount + self.profilePermanentUnavailableCount
                != self.recalledCount
            ):
                raise ValueError("selection profile resolution counts are inconsistent")
            if self.semanticResolvedCount + self.unresolvedCount != self.recalledCount:
                raise ValueError("selection semantic counts are inconsistent")
            if self.profileReboundCount + self.profileRebuiltCount > self.profileReadyCount:
                raise ValueError("selection profile cache counts are inconsistent")
            actual_gate_count = sum(item.gate is not None for item in self.assessments)
            if self.gateAssessedCount != actual_gate_count or self.gateAssessedCount > self.profileReadyCount:
                raise ValueError("selection assessment count is inconsistent")
            expected_profile_coverage = round(
                self.profileReadyCount / self.recalledCount if self.recalledCount else 1.0,
                6,
            )
            expected_assessment_coverage = round(
                self.gateAssessedCount / self.profileReadyCount if self.profileReadyCount else 0.0,
                6,
            )
            if (
                self.profileCoverage != expected_profile_coverage
                or self.assessmentCoverage != expected_assessment_coverage
            ):
                raise ValueError("selection coverage metrics are inconsistent")
            if self.failureHistogram != self.failureSummary:
                raise ValueError("selection failure histogram is inconsistent")
            retryable_count = sum(self.failureHistogram.get(code, 0) for code in _RETRYABLE_PROFILE_FAILURES)
            permanent_count = sum(self.failureHistogram.get(code, 0) for code in _PERMANENT_PROFILE_FAILURES)
            if (
                retryable_count != self.profileRetryableFailureCount
                or permanent_count != self.profilePermanentUnavailableCount
            ):
                raise ValueError("selection profile failure counts are inconsistent")
            systemic_threshold = max(5, math.ceil(self.recalledCount * 0.20))
            expected_systemic = sorted(
                code for code in _RETRYABLE_PROFILE_FAILURES if self.failureHistogram.get(code, 0) >= systemic_threshold
            )
            if self.systemicFailureCodes != expected_systemic:
                raise ValueError("selection systemic failure classification is inconsistent")
            healthy_gate = (
                self.profileCoverage >= 0.95
                and self.gateAssessedCount == self.profileReadyCount
                and not self.systemicFailureCodes
                and not self.negativeControlFailures
            )
            if self.publishedCount > 0 and healthy_gate:
                expected_state = "ready"
            elif (
                self.publishedCount == 0
                and healthy_gate
                and self.profileRetryableFailureCount == 0
                and self.semanticResolvedCount == self.recalledCount
            ):
                expected_state = "empty"
            else:
                expected_state = "degraded"
            if self.state != expected_state:
                raise ValueError("selection activation state is inconsistent")
            if self.currentEligible != (expected_state in {"ready", "empty"}):
                raise ValueError("selection activation eligibility is inconsistent")
        return self


class SelectionServingCard(StrictSelectionModel):
    githubRepositoryId: int = Field(gt=0)
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    htmlUrl: HttpUrl
    identitySummaryZh: str = Field(min_length=4, max_length=180)
    corePositioningZh: str | None = Field(default=None, min_length=4, max_length=500)
    whyWorthSeeingZh: str | None = Field(default=None, min_length=8, max_length=360)
    whyNowZh: str | None = Field(default=None, min_length=4, max_length=240)
    primaryReason: PrimaryReason
    supportingReasons: list[PrimaryReason] = Field(max_length=2)
    category: SelectionCategory
    categorySource: Literal["canonical_profile", "research_derived"]
    productFormsZh: list[str] = Field(max_length=3)
    primaryLanguage: str | None = Field(default=None, max_length=100)
    topics: list[str] = Field(max_length=12)
    licenseSpdxId: str | None = Field(default=None, max_length=100)
    totalStars: int = Field(ge=0)
    momentumLabel: str | None = Field(default=None, max_length=100)
    reusableAssets: list[str] = Field(max_length=3)
    bestFit: list[str] = Field(max_length=3)

    @model_validator(mode="after")
    def validate_identity(self) -> SelectionServingCard:
        url = self.htmlUrl
        if (
            url.scheme != "https"
            or url.host != "github.com"
            or url.username is not None
            or url.password is not None
            or url.query is not None
            or url.fragment is not None
            or url.path.rstrip("/") != f"/{self.repository}"
        ):
            raise ValueError("serving GitHub URL is not canonical")
        return self


class SelectionServingFile(StrictSelectionModel):
    path: str = Field(pattern=r"^[A-Za-z0-9._/-]+\.json$")
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    bytes: int = Field(ge=2, le=8 * 1024 * 1024)

    @model_validator(mode="after")
    def validate_path(self) -> SelectionServingFile:
        if self.path.startswith("/") or any(part in {"", ".", ".."} for part in self.path.split("/")):
            raise ValueError("selection serving path is unsafe")
        return self


class SelectionServingSnapshot(StrictSelectionModel):
    schemaVersion: Literal[1]
    selectionGenerationId: str
    sourceObservationSetId: str
    generatedAt: AwareDatetime
    latestCaptureId: str
    latestCaptureAt: AwareDatetime
    sourceWindowStart: AwareDatetime
    sourceWindowEnd: AwareDatetime
    status: Literal["ready", "empty", "degraded"]
    items: list[SelectionServingCard] = Field(max_length=20)
    categoryCounts: dict[SelectionCategory, int]
    primaryReasonCounts: dict[PrimaryReason, int]
    coverageLabelZh: str = Field(min_length=8, max_length=500)
    sourceCoverageState: Literal["healthy", "degraded"]
    sourceTodayGeneration: str
    candidateCount: int = Field(ge=0, le=500)
    recallCount: int = Field(default=0, ge=0, le=60)
    selectedCount: int = Field(ge=0, le=60)
    publishedCount: int = Field(ge=0, le=20)
    suppressedCount: int = Field(ge=0, le=60)
    currentGeneration: str | None = Field(default=None, max_length=190)
    latestAttemptGeneration: str | None = Field(default=None, max_length=190)
    profileReadyCount: int = Field(default=0, ge=0, le=60)
    profileReboundCount: int = Field(default=0, ge=0, le=60)
    profileRebuiltCount: int = Field(default=0, ge=0, le=60)
    retryableFailureCount: int = Field(default=0, ge=0, le=60)
    permanentFailureCount: int = Field(default=0, ge=0, le=60)
    profileCoverage: float = Field(default=1, ge=0, le=1)
    assessmentCoverage: float = Field(default=1, ge=0, le=1)
    systemicFailure: bool = False
    safeFailureCodes: list[str] = Field(default_factory=list, max_length=20)
    nextRetryAt: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_inventory(self) -> SelectionServingSnapshot:
        identifiers = [item.githubRepositoryId for item in self.items]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("selection cards must have unique identities")
        if self.status == "ready" and not self.items:
            raise ValueError("ready selection requires items")
        if self.status in {"empty", "degraded"} and self.items:
            raise ValueError("selection empty state is inconsistent")
        categories = {key: sum(item.category == key for item in self.items) for key in self.categoryCounts}
        reasons = {key: sum(item.primaryReason == key for item in self.items) for key in self.primaryReasonCounts}
        if (
            self.publishedCount != len(self.items)
            or self.selectedCount < self.publishedCount
            or self.categoryCounts != categories
            or self.primaryReasonCounts != reasons
        ):
            raise ValueError("selection serving counts are inconsistent")
        if self.latestAttemptGeneration is not None:
            if self.latestAttemptGeneration != self.selectionGenerationId:
                raise ValueError("selection latest attempt identity is inconsistent")
            if self.profileReadyCount + self.retryableFailureCount + self.permanentFailureCount != self.recallCount:
                raise ValueError("selection serving profile coverage is inconsistent")
            if self.currentGeneration != (self.selectionGenerationId if self.status in {"ready", "empty"} else None):
                raise ValueError("selection serving current eligibility is inconsistent")
        return self


class SelectionProjectContext(StrictSelectionModel):
    schemaVersion: Literal[1]
    selectionGenerationId: str
    sourceObservationSetId: str
    generatedAt: AwareDatetime
    card: SelectionServingCard
    selectionEvidenceDigest: str = Field(pattern=r"^[a-f0-9]{64}$")
    timelinessReasonCodes: list[str] = Field(min_length=1, max_length=6)
    evidence: list[SelectionEvidenceAlias] = Field(max_length=40)
    canonicalProfile: dict[str, Any]
    canonicalEvidence: dict[str, Any]


class SelectionServingManifest(StrictSelectionModel):
    schemaVersion: Literal[1]
    state: Literal["ready"]
    selectionGenerationId: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{1,190}$")
    sourceObservationSetId: str = Field(min_length=2, max_length=190)
    rawArtifactSha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    generatedAt: AwareDatetime
    files: list[SelectionServingFile] = Field(min_length=2, max_length=24)
    projectIds: list[int] = Field(max_length=20)

    @model_validator(mode="after")
    def validate_files(self) -> SelectionServingManifest:
        paths = [item.path for item in self.files]
        if len(paths) != len(set(paths)) or "serving/selection.json" not in paths or "raw/selection.json" not in paths:
            raise ValueError("selection manifest inventory is invalid")
        expected = {f"serving/projects/{identifier}.json" for identifier in self.projectIds}
        if not expected.issubset(paths):
            raise ValueError("selection project inventory is incomplete")
        return self


class SelectionServingPointer(StrictSelectionModel):
    schemaVersion: Literal[1]
    selectionGenerationId: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{1,190}$")
    sourceObservationSetId: str = Field(min_length=2, max_length=190)
    manifestSha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    activatedAt: AwareDatetime
    activationState: Literal["ready", "empty", "degraded"] | None = None
    activationPolicyVersion: Literal["worth-seeing-activation-v2"] | None = None


class SelectionApiResponse(StrictSelectionModel):
    mode: Literal["shadow"]
    status: Literal["ready", "empty", "degraded", "stale", "not_configured", "invalid"]
    state: Literal["ready", "empty", "degraded", "stale", "not_configured", "invalid"]
    generation: str | None
    sourceObservation: str | None
    sourceTodayGeneration: str | None
    generatedAt: AwareDatetime | None = None
    latestCaptureAt: AwareDatetime | None = None
    items: list[SelectionServingCard] = Field(max_length=20)
    categoryCounts: dict[str, int]
    primaryReasonCounts: dict[str, int]
    coverageLabelZh: str | None = Field(default=None, max_length=500)
    candidateCount: int = Field(ge=0, le=500)
    selectedCount: int = Field(ge=0, le=60)
    publishedCount: int = Field(ge=0, le=20)
    suppressedCount: int = Field(ge=0, le=60)
    provenance: dict[str, Any]
    code: str | None = Field(default=None, max_length=100)
    currentGeneration: str | None = Field(default=None, max_length=190)
    latestAttemptGeneration: str | None = Field(default=None, max_length=190)
    recallCount: int = Field(default=0, ge=0, le=60)
    profileReadyCount: int = Field(default=0, ge=0, le=60)
    profileReboundCount: int = Field(default=0, ge=0, le=60)
    profileRebuiltCount: int = Field(default=0, ge=0, le=60)
    retryableFailureCount: int = Field(default=0, ge=0, le=60)
    permanentFailureCount: int = Field(default=0, ge=0, le=60)
    profileCoverage: float = Field(default=1, ge=0, le=1)
    assessmentCoverage: float = Field(default=1, ge=0, le=1)
    systemicFailure: bool = False
    safeFailureCodes: list[str] = Field(default_factory=list, max_length=20)
    nextRetryAt: AwareDatetime | None = None
    productionReady: Literal[False] = False
    reviewable: bool = False
    shadowReviewState: Literal["ready", "empty", "incomplete", "invalid"] | None = None
    shadowReviewGeneration: str | None = None
    candidateUniverseCount: int = Field(default=0, ge=0, le=500)
    healthyProfileCount: int = Field(default=0, ge=0, le=60)
    unresolvedProfileCount: int = Field(default=0, ge=0, le=60)
    cohortSize: int = Field(default=0, ge=0, le=16)
    cohortAssessed: int = Field(default=0, ge=0, le=16)
    previewCount: int = Field(default=0, ge=0, le=6)
    providerBudget: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_state(self) -> SelectionApiResponse:
        if self.shadowReviewState is not None:
            if (
                self.state != "degraded"
                or self.currentGeneration is not None
                or self.generation != self.shadowReviewGeneration
                or self.cohortSize != 16
                or self.reviewable != (self.shadowReviewState in {"ready", "empty"})
                or self.healthyProfileCount + self.unresolvedProfileCount != self.recallCount
                or self.publishedCount > 6
                or self.previewCount != self.publishedCount
            ):
                raise ValueError("local shadow API contract is inconsistent")
            if self.reviewable and self.cohortAssessed != 16:
                raise ValueError("incomplete cohort cannot be reviewable")
            if (self.shadowReviewState == "ready") != bool(self.items):
                raise ValueError("shadow preview state is inconsistent")
        if self.status != self.state or self.publishedCount != len(self.items):
            raise ValueError("selection API state is inconsistent")
        if self.status == "ready" and (self.generation is None or not self.items):
            raise ValueError("ready Selection requires one generation and published items")
        if self.status == "stale" and self.generation is None:
            raise ValueError("stale Selection requires one generation")
        if self.status == "empty" and (self.generation is None or self.items):
            raise ValueError("empty Selection requires one generation and no items")
        if self.status == "degraded" and self.latestAttemptGeneration is None:
            raise ValueError("degraded Selection requires a latest attempt")
        if self.status in {"not_configured", "invalid"} and (self.generation is not None or self.items):
            raise ValueError("unavailable Selection cannot expose a generation")
        return self


class SelectionProjectDetail(StrictSelectionModel):
    selectionGenerationId: str
    sourceObservationSetId: str
    context: SelectionProjectContext
