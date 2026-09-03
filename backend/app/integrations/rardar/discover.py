"""Strict read-only consumer for Rardar's near-real-time Discover artifact."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import stat
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, model_validator

from app.integrations.rardar.adapter import (
    RardarArtifactError,
    _capture_payload_digest,
    _SafeRoot,
    _strict_json,
    _validate,
)

DISCOVER_ROOT = "artifacts/trending/discover/v1"
_DISCOVER_FILE = "discover.json"
_REPARSE_POINT = 0x400
_LEGACY_STAGE_KEYS = {
    "just_discovered": "justDiscovered",
    "rising": "rising",
    "near_validation": "nearValidation",
}
_STAGE_KEYS = {
    "just_discovered": "justDiscovered",
    "outside_today_momentum": "outsideTodayMomentum",
    "rising": "rising",
    "near_validation": "nearValidation",
}
_LEGACY_STAGE_SECTIONS = ("just_discovered", "rising", "near_validation")
_STAGE_SECTIONS = ("just_discovered", "outside_today_momentum", "rising", "near_validation")
_SIGNAL_FACT_ORDER = (
    "first_seen_recently",
    "outside_today_top20",
    "exact_rank_available",
    "recent_absolute_growth",
    "recent_relative_growth",
    "continuous_recent_growth",
    "recent_acceleration",
    "continuous_positive_growth",
    "absolute_growth_gate",
    "relative_growth_gate",
    "awaiting_today_settlement",
)


class StrictDiscoverModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


DiscoverSignalFact = Literal[
    "first_seen_recently",
    "outside_today_top20",
    "exact_rank_available",
    "recent_absolute_growth",
    "recent_relative_growth",
    "continuous_recent_growth",
    "recent_acceleration",
    "continuous_positive_growth",
    "absolute_growth_gate",
    "relative_growth_gate",
    "awaiting_today_settlement",
]


class DiscoverItem(StrictDiscoverModel):
    githubRepositoryId: int = Field(gt=0)
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    url: HttpUrl
    stage: Literal["just_discovered", "outside_today_momentum", "rising", "near_validation"]
    firstSeenAt: AwareDatetime
    lastObservedAt: AwareDatetime
    observedWindowStart: AwareDatetime
    observedWindowEnd: AwareDatetime
    observedWindowHours: float = Field(ge=0, le=27)
    observedStarDelta: int = Field(ge=0)
    totalStars: int = Field(ge=0)
    captureCount: int = Field(ge=1, le=14)
    consecutiveCaptureCount: int = Field(ge=1, le=14)
    language: str | None
    topics: list[str] = Field(max_length=100)
    license: str | None
    isFork: bool
    isArchived: bool
    isDisabled: Literal[False]
    latestPushAt: AwareDatetime
    sourceCaptureIds: list[str] = Field(min_length=1, max_length=14)
    sourceEvidenceDigest: str = Field(pattern=r"^[a-f0-9]{64}$")
    relativeGrowthPercent: float | None = Field(default=None, ge=0)
    positiveIntervalCount: int | None = Field(default=None, ge=0, le=13)
    consecutivePositiveIntervalCount: int | None = Field(default=None, ge=0, le=13)
    latestIntervalDelta: int | None = None
    publishReasonCodes: list[DiscoverSignalFact] | None = Field(default=None, min_length=1, max_length=11)
    signalFacts: list[DiscoverSignalFact] | None = Field(default=None, min_length=1, max_length=11)
    eligibilityClass: Literal["pre_exact", "exact_outside_published"] | None = None
    todayExactRank: int | None = Field(default=None, ge=21, le=500)
    todayExact24hDelta: int | None = Field(default=None, ge=0)
    recentWindowHours: float | None = Field(default=None, ge=0, le=4)
    recentObservedStarDelta: int | None = None
    priorComparableWindowDelta: int | None = None
    accelerationDelta: int | None = None
    recentRelativeGrowthPercent: float | None = None


class DiscoverCoverage(StrictDiscoverModel):
    state: Literal["healthy", "degraded"]
    querySuccessCount: int = Field(ge=1, le=9)
    queryFailureCount: int = Field(ge=0, le=8)
    metadataFailureCount: int = Field(ge=0, le=500)
    sourceCaptureCount: int = Field(ge=1, le=14)
    candidateCount: int = Field(ge=0, le=500)
    publishedCount: int = Field(ge=0, le=500)
    conflictCount: int = Field(ge=0, le=500)
    excludedExactCount: int | None = Field(default=None, ge=0, le=500)
    todayExactCount: int | None = Field(default=None, ge=0, le=500)
    todayPublishedCount: int | None = Field(default=None, ge=0, le=20)
    excludedPublishedCount: int | None = Field(default=None, ge=0, le=20)
    exactOutsidePublishedEvaluatedCount: int | None = Field(default=None, ge=0, le=500)
    preExactEvaluatedCount: int | None = Field(default=None, ge=0, le=500)
    invalidCount: int | None = Field(default=None, ge=0, le=500)


class DiscoverStageCounts(StrictDiscoverModel):
    justDiscovered: int = Field(ge=0, le=500)
    outsideTodayMomentum: int = Field(default=0, ge=0, le=500)
    rising: int = Field(ge=0, le=500)
    nearValidation: int = Field(ge=0, le=500)


class DiscoverSignalPolicy(StrictDiscoverModel):
    absoluteGrowthGateStars: int = Field(gt=0, le=100_000)
    relativeGrowthGatePercent: float = Field(gt=0, le=100_000)
    consecutivePositiveIntervalGate: int = Field(gt=0, le=13)
    recentDiscoveryHours: int = Field(gt=0, le=27)
    nearValidationHours: int = Field(gt=0, le=27)
    todayPublishedTopCount: Literal[20] | None = None
    outsideRecentWindowHours: Literal[4] | None = None
    outsideRequiresAcceleration: Literal[True] | None = None


class DiscoverSuppressionReasons(StrictDiscoverModel):
    weak_absolute_growth: int = Field(ge=0, le=500)
    weak_relative_growth: int = Field(ge=0, le=500)
    no_continuous_growth: int = Field(ge=0, le=500)
    already_in_today: int = Field(ge=0, le=500)
    identity_conflict: int = Field(ge=0, le=500)
    negative_growth: int = Field(ge=0, le=500)
    disabled: int = Field(ge=0, le=500)
    metadata_incomplete: int = Field(ge=0, le=500)


class DiscoverSuppressionSummary(StrictDiscoverModel):
    candidateCount: int = Field(ge=0, le=500)
    stageEligibleCount: int = Field(ge=0, le=500)
    publishedCount: int = Field(ge=0, le=500)
    suppressedWeakSignalCount: int = Field(ge=0, le=500)
    suppressedExactCount: int = Field(ge=0, le=500)
    conflictCount: int = Field(ge=0, le=500)
    reasons: DiscoverSuppressionReasons


class DiscoverSuppressionReasonsV3(StrictDiscoverModel):
    today_published: int = Field(ge=0, le=20)
    weak_recent_absolute_growth: int = Field(ge=0, le=500)
    weak_recent_relative_growth: int = Field(ge=0, le=500)
    no_recent_continuous_growth: int = Field(ge=0, le=500)
    no_recent_acceleration: int = Field(ge=0, le=500)
    weak_pre_exact_growth: int = Field(ge=0, le=500)
    already_exact_without_momentum: int = Field(ge=0, le=500)
    identity_conflict: int = Field(ge=0, le=500)
    negative_growth: int = Field(ge=0, le=500)
    disabled: int = Field(ge=0, le=500)
    metadata_incomplete: int = Field(ge=0, le=500)


class DiscoverSuppressionSummaryV3(StrictDiscoverModel):
    candidateCount: int = Field(ge=0, le=500)
    publishedCount: int = Field(ge=0, le=500)
    suppressedSignalCount: int = Field(ge=0, le=500)
    excludedPublishedCount: int = Field(ge=0, le=20)
    conflictCount: int = Field(ge=0, le=500)
    reasons: DiscoverSuppressionReasonsV3


class DiscoverEligibilityCounts(StrictDiscoverModel):
    todayPublished: int = Field(ge=0, le=20)
    exactOutsidePublished: int = Field(ge=0, le=500)
    preExact: int = Field(ge=0, le=500)
    invalid: int = Field(ge=0, le=500)


class DiscoverBoard(StrictDiscoverModel):
    schemaVersion: Literal[1, 2, 3]
    policyVersion: Literal["trending-discover-v1", "trending-discover-v2", "trending-discover-v3"]
    discoverGenerationId: str
    generatedAt: AwareDatetime
    latestCaptureId: str
    latestCaptureScheduledAt: AwareDatetime
    latestCaptureCapturedAt: AwareDatetime
    sourceWindowStart: AwareDatetime
    sourceWindowEnd: AwareDatetime
    sourceCaptureCount: int = Field(ge=1, le=14)
    todayExplosionGenerationId: str
    todayExplosionDigest: str = Field(pattern=r"^[a-f0-9]{64}$")
    updateCadenceMinutes: Literal[120]
    justDiscovered: list[DiscoverItem] = Field(max_length=500)
    outsideTodayMomentum: list[DiscoverItem] = Field(default_factory=list, max_length=500)
    rising: list[DiscoverItem] = Field(max_length=500)
    nearValidation: list[DiscoverItem] = Field(max_length=500)
    coverage: DiscoverCoverage
    conflictCount: int = Field(ge=0, le=500)
    conflictReasons: dict[str, int]
    stageCounts: DiscoverStageCounts
    signalPolicy: DiscoverSignalPolicy | None = None
    suppressionSummary: DiscoverSuppressionSummary | DiscoverSuppressionSummaryV3 | None = None
    todayExactCount: int | None = Field(default=None, ge=0, le=500)
    todayPublishedTopCount: Literal[20] | None = None
    todayPublishedCount: int | None = Field(default=None, ge=0, le=20)
    todayPublishedSetDigest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    excludedPublishedCount: int | None = Field(default=None, ge=0, le=20)
    exactOutsidePublishedEvaluatedCount: int | None = Field(default=None, ge=0, le=500)
    preExactEvaluatedCount: int | None = Field(default=None, ge=0, le=500)
    eligibilityCounts: DiscoverEligibilityCounts | None = None
    payloadDigest: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_policy_projection(self) -> DiscoverBoard:
        if self.schemaVersion == 1:
            if self.policyVersion != "trending-discover-v1" or self.signalPolicy or self.suppressionSummary:
                raise ValueError("Discover v1 projection contains v2 policy fields")
        elif self.schemaVersion == 2 and (
            self.policyVersion != "trending-discover-v2" or self.signalPolicy is None or self.suppressionSummary is None
        ):
            raise ValueError("Discover v2 projection is missing policy fields")
        elif self.schemaVersion == 3 and (
            self.policyVersion != "trending-discover-v3"
            or self.signalPolicy is None
            or not isinstance(self.suppressionSummary, DiscoverSuppressionSummaryV3)
            or self.todayPublishedTopCount != 20
            or self.todayExactCount is None
            or self.todayPublishedCount is None
            or self.todayPublishedSetDigest is None
            or self.excludedPublishedCount is None
            or self.exactOutsidePublishedEvaluatedCount is None
            or self.preExactEvaluatedCount is None
            or self.eligibilityCounts is None
        ):
            raise ValueError("Discover v3 projection is missing eligibility fields")
        return self


@dataclass(frozen=True)
class DiscoverSourceProject:
    item: DiscoverItem
    description: str | None
    forks: int
    default_branch: str


@dataclass(frozen=True)
class LoadedDiscoverArtifact:
    board: DiscoverBoard
    pointer_raw: bytes
    manifest_sha256: str
    artifact_sha256: str
    projects: dict[int, DiscoverSourceProject]
    # Selection Runtime needs the complete, already schema/hash/audit-validated
    # source universe rather than the legacy momentum publication subset.
    captures: tuple[dict[str, Any], ...]
    today: dict[str, Any]


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _payload_digest(value: dict[str, Any]) -> str:
    return _sha(_canonical_bytes({key: item for key, item in value.items() if key != "payloadDigest"}))


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp has no timezone")
    return parsed


def _is_reparse(info: os.stat_result) -> bool:
    return bool(getattr(info, "st_file_attributes", 0) & _REPARSE_POINT)


class DiscoverArtifactAdapter:
    """Bind a request to one immutable, fully re-audited Discover generation."""

    def __init__(self, root: _SafeRoot) -> None:
        self._root = root

    @classmethod
    def from_config(cls, configured: str) -> DiscoverArtifactAdapter:
        return cls(_SafeRoot(configured))

    def _json(self, relative: str, maximum: int, label: str) -> tuple[dict[str, Any], bytes]:
        try:
            raw = self._root.read_stable(relative, maximum_bytes=maximum)
            return _strict_json(raw), raw
        except RardarArtifactError:
            raise
        except (FileNotFoundError, OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            raise RardarArtifactError("rardar_discover_invalid", f"Rardar Discover {label} is invalid") from exc

    @staticmethod
    def _schema(name: str, value: dict[str, Any], label: str) -> None:
        try:
            _validate(name, value)
        except Exception as exc:
            raise RardarArtifactError("rardar_discover_invalid", f"Rardar Discover {label} failed Schema") from exc

    def _inventory(self, generation_id: str) -> dict[str, str]:
        relative_root = f"{DISCOVER_ROOT}/generations/{generation_id}"
        generation_root = self._root.path(relative_root)
        try:
            self._root._assert_component_chain(generation_root, final_kind="directory")
            inventory: dict[str, str] = {}
            for directory, directories, filenames in os.walk(generation_root, followlinks=False):
                current = Path(directory)
                info = os.lstat(current)
                if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or _is_reparse(info):
                    raise ValueError("unsafe generation directory")
                for name in directories:
                    child = current / name
                    child_info = os.lstat(child)
                    if (
                        not stat.S_ISDIR(child_info.st_mode)
                        or stat.S_ISLNK(child_info.st_mode)
                        or _is_reparse(child_info)
                    ):
                        raise ValueError("unsafe generation directory")
                for name in filenames:
                    path = current / name
                    file_info = os.lstat(path)
                    if not stat.S_ISREG(file_info.st_mode) or stat.S_ISLNK(file_info.st_mode) or _is_reparse(file_info):
                        raise ValueError("unsafe generation file")
                    relative = path.relative_to(generation_root).as_posix()
                    if name.startswith(".") and name.endswith(".tmp"):
                        raise ValueError("temporary file in generation")
                    if relative != "manifest.json":
                        raw = self._root.read_stable(f"{relative_root}/{relative}", maximum_bytes=16 * 1024 * 1024)
                        inventory[relative] = _sha(raw)
            return inventory
        except (FileNotFoundError, OSError, ValueError) as exc:
            raise RardarArtifactError("rardar_discover_invalid", "Rardar Discover generation layout is unsafe") from exc

    def load(self) -> LoadedDiscoverArtifact:
        self._root.ensure_available()
        pointer_path = f"{DISCOVER_ROOT}/current.json"
        try:
            pointer, pointer_raw = self._json(pointer_path, 64 * 1024, "pointer")
        except RardarArtifactError as exc:
            if exc.__cause__ and isinstance(exc.__cause__, FileNotFoundError):
                raise RardarArtifactError(
                    "rardar_discover_not_configured", "Rardar Discover is not synchronized"
                ) from exc
            raise
        self._schema("trending-discover-current.schema.json", pointer, "pointer")
        generation_id = pointer["generationId"]
        base = f"{DISCOVER_ROOT}/generations/{generation_id}"
        manifest, manifest_raw = self._json(f"{base}/manifest.json", 4 * 1024 * 1024, "manifest")
        if _sha(manifest_raw) != pointer["manifestSha256"]:
            raise RardarArtifactError("rardar_discover_invalid", "Rardar Discover manifest digest is invalid")
        self._schema("trending-discover-manifest.schema.json", manifest, "manifest")
        if manifest["generationId"] != generation_id or manifest["state"] != "ready":
            raise RardarArtifactError("rardar_discover_invalid", "Rardar Discover generation identity is invalid")
        inventory = self._inventory(generation_id)
        if inventory != manifest["artifacts"]:
            raise RardarArtifactError("rardar_discover_invalid", "Rardar Discover inventory is invalid")
        artifact, artifact_raw = self._json(f"{base}/{_DISCOVER_FILE}", 16 * 1024 * 1024, "artifact")
        self._schema("trending-discover-artifact.schema.json", artifact, "artifact")
        if manifest["artifacts"].get(_DISCOVER_FILE) != _sha(artifact_raw):
            raise RardarArtifactError("rardar_discover_invalid", "Rardar Discover artifact hash is invalid")
        if (
            artifact["discoverGenerationId"] != generation_id
            or _payload_digest(artifact) != artifact["payloadDigest"]["value"]
            or pointer["schemaVersion"] != manifest["schemaVersion"]
            or pointer["schemaVersion"] != artifact["schemaVersion"]
            or pointer["policyVersion"] != manifest["policyVersion"]
            or pointer["policyVersion"] != artifact["policyVersion"]
        ):
            raise RardarArtifactError("rardar_discover_invalid", "Rardar Discover payload binding is invalid")

        captures = self._load_captures(base, artifact, manifest)
        today = self._load_today(base, artifact, manifest)
        if artifact["policyVersion"] == "trending-discover-v1":
            rebuilt, source_projects = self._rebuild_v1(artifact, captures, today)
            if rebuilt != artifact:
                raise RardarArtifactError("rardar_discover_invalid", "Rardar Discover source recomputation failed")
        elif artifact["policyVersion"] == "trending-discover-v2":
            source_projects = self._audit_v2(artifact, captures, today)
        else:
            source_projects = self._audit_v3(artifact, captures, today)
        expected_audit = {
            "status": artifact["coverage"]["state"],
            "validatedSourceCount": artifact["sourceCaptureCount"] + 1,
            "publishedCount": artifact["coverage"]["publishedCount"],
            "conflictCount": artifact["coverage"]["conflictCount"],
        }
        if artifact["policyVersion"] == "trending-discover-v2":
            expected_audit["suppressedWeakSignalCount"] = artifact["suppressionSummary"]["suppressedWeakSignalCount"]
        elif artifact["policyVersion"] == "trending-discover-v3":
            expected_audit.update(
                {
                    "suppressedSignalCount": artifact["suppressionSummary"]["suppressedSignalCount"],
                    "excludedPublishedCount": artifact["excludedPublishedCount"],
                    "exactOutsidePublishedEvaluatedCount": artifact["exactOutsidePublishedEvaluatedCount"],
                    "outsideTodayMomentumCount": len(artifact["stages"]["outsideTodayMomentum"]),
                }
            )
        if manifest["audit"] != expected_audit:
            raise RardarArtifactError("rardar_discover_invalid", "Rardar Discover manifest audit is inconsistent")
        board = self._project_board(artifact)
        return LoadedDiscoverArtifact(
            board=board,
            pointer_raw=pointer_raw,
            manifest_sha256=_sha(manifest_raw),
            artifact_sha256=_sha(artifact_raw),
            projects=source_projects,
            captures=tuple(entry[0] for entry in captures),
            today=today[0],
        )

    def _load_captures(
        self, base: str, artifact: dict[str, Any], manifest: dict[str, Any]
    ) -> list[tuple[dict[str, Any], bytes, dict[str, Any]]]:
        captures: list[tuple[dict[str, Any], bytes, dict[str, Any]]] = []
        previous: datetime | None = None
        for reference in artifact["sourceInventory"]:
            canonical = artifact["policyVersion"] == "trending-discover-v3"
            relative = reference["originalObservationPath"] if canonical else reference["generationRelativePath"]
            payload, raw = self._json(
                relative if canonical else f"{base}/{relative}", 16 * 1024 * 1024, "source capture"
            )
            self._schema("trending-capture-bundle.schema.json", payload, "source capture")
            if (
                (not canonical and manifest["artifacts"].get(relative) != _sha(raw))
                or reference["fileSha256"] != _sha(raw)
                or _capture_payload_digest(payload) != payload["digest"]["value"]
                or payload["digest"]["value"] != reference["payloadDigestSha256"]
                or payload["captureId"] != reference["captureId"]
                or payload["scheduledAt"] != reference["scheduledAt"]
                or payload["capturedAt"] != reference["capturedAt"]
                or payload["coverageState"] != reference["coverageState"]
                or payload["windowEligible"] is not True
            ):
                raise RardarArtifactError("rardar_discover_invalid", "Rardar Discover source capture is inconsistent")
            scheduled = _timestamp(payload["scheduledAt"])
            if previous is not None and scheduled <= previous:
                raise RardarArtifactError("rardar_discover_invalid", "Rardar Discover source order is invalid")
            previous = scheduled
            captures.append((payload, raw, reference))
        return captures

    def _load_today(
        self, base: str, artifact: dict[str, Any], manifest: dict[str, Any]
    ) -> tuple[dict[str, Any], bytes, dict[str, Any]]:
        reference = artifact["todayExplosionSource"]
        manifest_relative = reference["generationManifestRelativePath"]
        today_manifest, today_manifest_raw = self._json(
            f"{base}/{manifest_relative}", 4 * 1024 * 1024, "Today manifest"
        )
        self._schema("generation-manifest.schema.json", today_manifest, "Today manifest")
        today_relative = reference["generationRelativePath"]
        today, today_raw = self._json(f"{base}/{today_relative}", 16 * 1024 * 1024, "Today artifact")
        self._schema("trending-explosion-artifact.schema.json", today, "Today artifact")
        if (
            manifest["artifacts"].get(manifest_relative) != _sha(today_manifest_raw)
            or manifest["artifacts"].get(today_relative) != _sha(today_raw)
            or _sha(today_manifest_raw) != reference["generationManifestSha256"]
            or _sha(today_raw) != reference["fileSha256"]
            or _sha(today_raw) != artifact["todayExplosionDigest"]
            or today_manifest["generationId"] != reference["generationId"]
            or today_manifest["state"] != "ready"
            or "trending/explosion.json" not in today_manifest["artifacts"]
            or today_manifest["hashes"].get("trending/explosion.json") != _sha(today_raw)
            or today["generationId"] != reference["generationId"]
            or artifact["todayExplosionGenerationId"] != reference["generationId"]
            or today["window"]["endedAt"] != reference["windowEndedAt"]
            or len(today["exactRanked"]) != reference["exactCount"]
        ):
            raise RardarArtifactError("rardar_discover_invalid", "Rardar Discover Today exclusion is inconsistent")
        return today, today_raw, reference

    @staticmethod
    def _observation_index(payload: dict[str, Any]) -> dict[int, dict[str, Any]]:
        values: dict[int, dict[str, Any]] = {}
        for item in payload["observations"]:
            repository_id = int(item["githubRepositoryId"])
            if repository_id in values:
                raise RardarArtifactError("rardar_discover_invalid", "Duplicate repository identity in capture")
            values[repository_id] = item
        return values

    @staticmethod
    def _evidence_digest(observations: list[tuple[dict[str, Any], dict[str, Any]]]) -> str:
        return _sha(
            _canonical_bytes(
                [
                    {
                        "captureId": source["captureId"],
                        "githubRepositoryId": item["githubRepositoryId"],
                        "repository": item["repository"],
                        "totalStars": item["totalStars"],
                    }
                    for source, item in observations
                ]
            )
        )

    @staticmethod
    def _positive_interval_facts(
        observations: list[tuple[dict[str, Any], dict[str, Any]]],
    ) -> tuple[int, int, int | None]:
        positive_count = 0
        longest_run = 0
        current_run = 0
        latest_delta: int | None = None
        pairs = list(zip(observations, observations[1:], strict=False))
        for index, ((previous_source, previous), (current_source, current)) in enumerate(pairs):
            if _timestamp(current_source["scheduledAt"]) - _timestamp(previous_source["scheduledAt"]) != timedelta(
                minutes=120
            ):
                current_run = 0
                if index == len(pairs) - 1:
                    latest_delta = None
                continue
            interval_delta = int(current["totalStars"]) - int(previous["totalStars"])
            if index == len(pairs) - 1:
                latest_delta = interval_delta
            if interval_delta > 0:
                positive_count += 1
                current_run += 1
                longest_run = max(longest_run, current_run)
            else:
                current_run = 0
        return positive_count, longest_run, latest_delta

    @classmethod
    def _comparable_window_facts(
        cls,
        observations: list[tuple[dict[str, Any], dict[str, Any]]],
        *,
        latest_scheduled_at: datetime,
    ) -> tuple[int | None, int | None, int | None, float | None, int]:
        recent_start = latest_scheduled_at - timedelta(hours=4)
        prior_start = recent_start - timedelta(hours=4)
        recent = [
            value
            for value in observations
            if recent_start <= _timestamp(value[0]["scheduledAt"]) <= latest_scheduled_at
        ]
        prior = [value for value in observations if prior_start <= _timestamp(value[0]["scheduledAt"]) <= recent_start]

        def complete_delta(values: list[tuple[dict[str, Any], dict[str, Any]]]) -> int | None:
            if len(values) != 3 or any(
                _timestamp(current[0]["scheduledAt"]) - _timestamp(previous[0]["scheduledAt"]) != timedelta(minutes=120)
                for previous, current in zip(values, values[1:], strict=False)
            ):
                return None
            return int(values[-1][1]["totalStars"]) - int(values[0][1]["totalStars"])

        recent_delta = complete_delta(recent)
        prior_delta = complete_delta(prior)
        acceleration = recent_delta - prior_delta if recent_delta is not None and prior_delta is not None else None
        relative = (
            round(recent_delta / int(recent[0][1]["totalStars"]) * 100, 6)
            if recent_delta is not None and recent and int(recent[0][1]["totalStars"]) > 0
            else None
        )
        _, consecutive, _ = cls._positive_interval_facts(recent)
        return recent_delta, prior_delta, acceleration, relative, consecutive

    @staticmethod
    def _consecutive_capture_count(
        repository_id: int,
        payloads: list[dict[str, Any]],
        indexes: list[dict[int, dict[str, Any]]],
    ) -> int:
        consecutive = 0
        previous: datetime | None = None
        for payload, index in reversed(list(zip(payloads, indexes, strict=True))):
            if repository_id not in index:
                break
            scheduled = _timestamp(payload["scheduledAt"])
            if previous is not None and previous - scheduled != timedelta(minutes=120):
                break
            consecutive += 1
            previous = scheduled
        return consecutive

    @staticmethod
    def _ordered_signal_facts(values: set[str]) -> list[str]:
        return [value for value in _SIGNAL_FACT_ORDER if value in values]

    def _audit_v2(
        self,
        artifact: dict[str, Any],
        captures: list[tuple[dict[str, Any], bytes, dict[str, Any]]],
        today_source: tuple[dict[str, Any], bytes, dict[str, Any]],
    ) -> dict[int, DiscoverSourceProject]:
        """Re-audit published facts without duplicating Rardar's candidate selector."""

        payloads = [entry[0] for entry in captures]
        indexes = [self._observation_index(payload) for payload in payloads]
        latest = payloads[-1]
        latest_index = indexes[-1]
        today, today_raw, today_reference = today_source
        exact_ids = {int(item["githubRepositoryId"]) for item in today["exactRanked"]}
        policy = artifact["signalPolicy"]
        expected_policy = {
            "absoluteGrowthGateStars": 10,
            "relativeGrowthGatePercent": 1.0,
            "consecutivePositiveIntervalGate": 2,
            "recentDiscoveryHours": 4,
            "nearValidationHours": 20,
        }
        if policy != expected_policy:
            raise RardarArtifactError("rardar_discover_invalid", "Rardar Discover v2 policy is unsupported")
        expected_header = {
            "latestCaptureId": latest["captureId"],
            "latestCaptureScheduledAt": latest["scheduledAt"],
            "latestCaptureCapturedAt": latest["capturedAt"],
            "sourceWindowStart": payloads[0]["capturedAt"],
            "sourceWindowEnd": latest["capturedAt"],
            "sourceCaptureCount": len(payloads),
            "todayExplosionGenerationId": today_reference["generationId"],
            "todayExplosionDigest": _sha(today_raw),
            "updateCadenceMinutes": 120,
        }
        if any(artifact[key] != value for key, value in expected_header.items()):
            raise RardarArtifactError("rardar_discover_invalid", "Rardar Discover v2 source header is inconsistent")

        name_ids: dict[str, set[int]] = {}
        for index in indexes:
            for repository_id, item in index.items():
                name_ids.setdefault(str(item["repository"]).casefold(), set()).add(repository_id)

        expected_conflicts: list[dict[str, Any]] = []
        excluded_exact = 0
        for repository_id, current in latest_index.items():
            observations = [
                (payload, index[repository_id])
                for payload, index in zip(payloads, indexes, strict=True)
                if repository_id in index
            ]
            first = observations[0][1]
            capture_ids = [source["captureId"] for source, _ in observations]
            if any(len(name_ids[str(item["repository"]).casefold()]) != 1 for _, item in observations):
                expected_conflicts.append(
                    {
                        "reason": "source_identity_conflict",
                        "githubRepositoryId": repository_id,
                        "repository": current["repository"],
                        "currentStars": current["totalStars"],
                        "baselineStars": first["totalStars"],
                        "sourceCaptureIds": capture_ids,
                    }
                )
                continue
            if current["disabled"] is True:
                expected_conflicts.append(
                    {
                        "reason": "current_disabled",
                        "githubRepositoryId": repository_id,
                        "repository": current["repository"],
                        "currentStars": current["totalStars"],
                        "baselineStars": first["totalStars"],
                        "sourceCaptureIds": capture_ids,
                    }
                )
                continue
            if repository_id in exact_ids:
                excluded_exact += 1
                continue
            if int(current["totalStars"]) - int(first["totalStars"]) < 0:
                expected_conflicts.append(
                    {
                        "reason": "star_count_decreased",
                        "githubRepositoryId": repository_id,
                        "repository": current["repository"],
                        "currentStars": current["totalStars"],
                        "baselineStars": first["totalStars"],
                        "sourceCaptureIds": capture_ids,
                    }
                )
        expected_conflicts.sort(key=lambda item: (item["reason"], item["repository"], item["githubRepositoryId"]))
        if artifact["conflicts"] != expected_conflicts:
            raise RardarArtifactError("rardar_discover_invalid", "Rardar Discover v2 conflicts are inconsistent")
        conflicting_ids = {int(item["githubRepositoryId"]) for item in expected_conflicts}

        source_projects: dict[int, DiscoverSourceProject] = {}
        published_ids: list[int] = []
        for stage, key in _LEGACY_STAGE_KEYS.items():
            raw_items = artifact["stages"][key]
            expected_order = sorted(
                raw_items,
                key=lambda item: (-item["observedStarDelta"], -item["totalStars"], item["repository"]),
            )
            if raw_items != expected_order:
                raise RardarArtifactError("rardar_discover_invalid", "Rardar Discover v2 order is inconsistent")
            for raw_item in raw_items:
                repository_id = int(raw_item["githubRepositoryId"])
                if repository_id in exact_ids or repository_id not in latest_index:
                    raise RardarArtifactError("rardar_discover_invalid", "Rardar Discover v2 Today exclusion failed")
                if repository_id in conflicting_ids:
                    raise RardarArtifactError("rardar_discover_invalid", "Rardar Discover v2 conflict exclusion failed")
                current = latest_index[repository_id]
                observations = [
                    (payload, index[repository_id])
                    for payload, index in zip(payloads, indexes, strict=True)
                    if repository_id in index
                ]
                first_source, first = observations[0]
                delta = int(current["totalStars"]) - int(first["totalStars"])
                hours = round(
                    (_timestamp(latest["capturedAt"]) - _timestamp(first_source["capturedAt"])).total_seconds() / 3600,
                    6,
                )
                consecutive = self._consecutive_capture_count(repository_id, payloads, indexes)
                consecutive_start = payloads[len(payloads) - consecutive]
                consecutive_hours = (
                    _timestamp(latest["capturedAt"]) - _timestamp(consecutive_start["capturedAt"])
                ).total_seconds() / 3600
                positive_count, longest_run, latest_delta = self._positive_interval_facts(observations)
                relative = round(delta / int(first["totalStars"]) * 100, 6) if int(first["totalStars"]) > 0 else None
                recent = _timestamp(latest["scheduledAt"]) - _timestamp(first_source["scheduledAt"]) <= timedelta(
                    hours=policy["recentDiscoveryHours"]
                )
                absolute_gate = delta >= policy["absoluteGrowthGateStars"]
                relative_gate = relative is not None and relative >= policy["relativeGrowthGatePercent"]
                continuous_gate = longest_run >= policy["consecutivePositiveIntervalGate"]
                quality_gate = (absolute_gate or relative_gate) and continuous_gate
                near = consecutive_hours >= policy["nearValidationHours"]
                rising = len(observations) >= 3 and hours > 0 and delta > 0
                expected_stage = (
                    "just_discovered"
                    if recent
                    else "near_validation"
                    if near and quality_gate
                    else "rising"
                    if rising and quality_gate
                    else None
                )
                facts: set[str] = {"first_seen_recently"} if recent else set()
                if expected_stage in {"rising", "near_validation"}:
                    facts.add("continuous_positive_growth")
                    if absolute_gate:
                        facts.add("absolute_growth_gate")
                    if relative_gate:
                        facts.add("relative_growth_gate")
                    if expected_stage == "near_validation":
                        facts.add("awaiting_today_settlement")
                signal_facts = self._ordered_signal_facts(facts)
                expected_item = {
                    "githubRepositoryId": repository_id,
                    "repository": current["repository"],
                    "url": current["htmlUrl"],
                    "stage": expected_stage,
                    "firstSeenAt": first_source["capturedAt"],
                    "lastObservedAt": latest["capturedAt"],
                    "observedWindowStart": first_source["capturedAt"],
                    "observedWindowEnd": latest["capturedAt"],
                    "observedWindowHours": hours,
                    "observedStarDelta": delta,
                    "totalStars": current["totalStars"],
                    "captureCount": len(observations),
                    "consecutiveCaptureCount": consecutive,
                    "language": current["primaryLanguage"],
                    "topics": copy.deepcopy(current["topics"]),
                    "license": current["licenseSpdxId"],
                    "isFork": current["fork"],
                    "isArchived": current["archived"],
                    "isDisabled": False,
                    "latestPushAt": current["pushedAt"],
                    "sourceCaptureIds": [source["captureId"] for source, _ in observations],
                    "sourceEvidenceDigest": self._evidence_digest(observations),
                    "relativeGrowthPercent": relative,
                    "positiveIntervalCount": positive_count,
                    "consecutivePositiveIntervalCount": longest_run,
                    "latestIntervalDelta": latest_delta,
                    "publishReasonCodes": signal_facts,
                    "signalFacts": signal_facts,
                }
                if expected_stage != stage or raw_item != expected_item:
                    raise RardarArtifactError(
                        "rardar_discover_invalid", "Rardar Discover v2 published facts are inconsistent"
                    )
                item = DiscoverItem.model_validate_json(json.dumps(raw_item), strict=True)
                source_projects[repository_id] = DiscoverSourceProject(
                    item=item,
                    description=current.get("description"),
                    forks=int(current.get("forks", 0)),
                    default_branch=str(current.get("defaultBranch") or "main"),
                )
                published_ids.append(repository_id)

        if len(published_ids) != len(set(published_ids)):
            raise RardarArtifactError("rardar_discover_invalid", "Rardar Discover v2 identity is duplicated")
        coverage = artifact["coverage"]
        expected_coverage = {
            "state": "degraded" if any(payload["coverageState"] == "degraded" for payload in payloads) else "healthy",
            "querySuccessCount": latest["successfulQueryCount"],
            "queryFailureCount": latest["failedQueryCount"],
            "metadataFailureCount": latest["metadataFailureCount"],
            "sourceCaptureCount": len(payloads),
            "candidateCount": len(latest_index),
            "publishedCount": len(published_ids),
            "conflictCount": len(expected_conflicts),
            "excludedExactCount": excluded_exact,
        }
        if coverage != expected_coverage:
            raise RardarArtifactError("rardar_discover_invalid", "Rardar Discover v2 coverage is inconsistent")
        summary = artifact["suppressionSummary"]
        reasons = summary["reasons"]
        conflict_reason_counts = {
            "identity_conflict": sum(item["reason"] == "source_identity_conflict" for item in expected_conflicts),
            "negative_growth": sum(item["reason"] == "star_count_decreased" for item in expected_conflicts),
            "disabled": sum(item["reason"] == "current_disabled" for item in expected_conflicts),
        }
        weak_reason_total = sum(
            int(reasons[key]) for key in ("weak_absolute_growth", "weak_relative_growth", "no_continuous_growth")
        )
        if (
            summary["candidateCount"] != len(latest_index)
            or summary["publishedCount"] != len(published_ids)
            or summary["suppressedExactCount"] != excluded_exact
            or summary["conflictCount"] != len(expected_conflicts)
            or summary["stageEligibleCount"] != summary["publishedCount"] + summary["suppressedWeakSignalCount"]
            or summary["stageEligibleCount"] > summary["candidateCount"]
            or any(
                reasons[key] > summary["suppressedWeakSignalCount"]
                for key in ("weak_absolute_growth", "weak_relative_growth", "no_continuous_growth")
            )
            or (
                summary["suppressedWeakSignalCount"] > 0
                and not (
                    summary["suppressedWeakSignalCount"]
                    <= weak_reason_total
                    <= summary["suppressedWeakSignalCount"] * 3
                )
            )
            or (summary["suppressedWeakSignalCount"] == 0 and weak_reason_total != 0)
            or reasons["already_in_today"] != excluded_exact
            or reasons["metadata_incomplete"] != latest["metadataFailureCount"]
            or any(reasons[key] != value for key, value in conflict_reason_counts.items())
        ):
            raise RardarArtifactError("rardar_discover_invalid", "Rardar Discover v2 suppression audit is inconsistent")
        return source_projects

    def _audit_v3(
        self,
        artifact: dict[str, Any],
        captures: list[tuple[dict[str, Any], bytes, dict[str, Any]]],
        today_source: tuple[dict[str, Any], bytes, dict[str, Any]],
    ) -> dict[int, DiscoverSourceProject]:
        """Validate the producer-issued v3 proof without selecting additional candidates."""

        payloads = [entry[0] for entry in captures]
        indexes = [self._observation_index(payload) for payload in payloads]
        latest = payloads[-1]
        latest_index = indexes[-1]
        today, today_raw, today_reference = today_source
        exact_by_id = {int(item["githubRepositoryId"]): item for item in today["exactRanked"]}
        if len(exact_by_id) != len(today["exactRanked"]):
            raise RardarArtifactError("rardar_discover_invalid", "Rardar Discover Today identities are duplicated")
        published_ranks = sorted(int(item["rank"]) for item in today["exactRanked"] if int(item["rank"]) <= 20)
        if published_ranks != list(range(1, 21)):
            raise RardarArtifactError(
                "rardar_discover_invalid",
                "Rardar Discover Today published rank boundary is incomplete",
            )
        published_ids = {repository_id for repository_id, item in exact_by_id.items() if int(item["rank"]) <= 20}
        published_digest = _sha(_canonical_bytes(sorted(published_ids)))
        expected_policy = {
            "absoluteGrowthGateStars": 10,
            "relativeGrowthGatePercent": 1.0,
            "consecutivePositiveIntervalGate": 2,
            "recentDiscoveryHours": 4,
            "nearValidationHours": 20,
            "todayPublishedTopCount": 20,
            "outsideRecentWindowHours": 4,
            "outsideRequiresAcceleration": True,
        }
        if artifact["signalPolicy"] != expected_policy:
            raise RardarArtifactError("rardar_discover_invalid", "Rardar Discover v3 policy is unsupported")
        expected_header = {
            "latestCaptureId": latest["captureId"],
            "latestCaptureScheduledAt": latest["scheduledAt"],
            "latestCaptureCapturedAt": latest["capturedAt"],
            "sourceWindowStart": payloads[0]["capturedAt"],
            "sourceWindowEnd": latest["capturedAt"],
            "sourceCaptureCount": len(payloads),
            "todayExplosionGenerationId": today_reference["generationId"],
            "todayExplosionDigest": _sha(today_raw),
            "updateCadenceMinutes": 120,
            "todayExactCount": len(exact_by_id),
            "todayPublishedTopCount": 20,
            "todayPublishedCount": len(published_ids),
            "todayPublishedSetDigest": published_digest,
        }
        if any(artifact[key] != value for key, value in expected_header.items()):
            raise RardarArtifactError("rardar_discover_invalid", "Rardar Discover v3 source header is inconsistent")

        name_ids: dict[str, set[int]] = {}
        for index in indexes:
            for repository_id, item in index.items():
                name_ids.setdefault(str(item["repository"]).casefold(), set()).add(repository_id)

        expected_conflicts: list[dict[str, Any]] = []
        eligibility = {"todayPublished": 0, "exactOutsidePublished": 0, "preExact": 0, "invalid": 0}
        suppression_reasons = {
            "today_published": 0,
            "weak_recent_absolute_growth": 0,
            "weak_recent_relative_growth": 0,
            "no_recent_continuous_growth": 0,
            "no_recent_acceleration": 0,
            "weak_pre_exact_growth": 0,
            "already_exact_without_momentum": 0,
            "identity_conflict": 0,
            "negative_growth": 0,
            "disabled": 0,
            "metadata_incomplete": int(latest["metadataFailureCount"]),
        }
        candidate_facts: dict[int, dict[str, Any]] = {}
        for repository_id, current in latest_index.items():
            observations = [
                (payload, index[repository_id])
                for payload, index in zip(payloads, indexes, strict=True)
                if repository_id in index
            ]
            first = observations[0][1]
            capture_ids = [source["captureId"] for source, _ in observations]
            if any(len(name_ids[str(item["repository"]).casefold()]) != 1 for _, item in observations):
                suppression_reasons["identity_conflict"] += 1
                eligibility["invalid"] += 1
                expected_conflicts.append(
                    {
                        "reason": "source_identity_conflict",
                        "githubRepositoryId": repository_id,
                        "repository": current["repository"],
                        "currentStars": current["totalStars"],
                        "baselineStars": first["totalStars"],
                        "sourceCaptureIds": capture_ids,
                    }
                )
                continue
            if current["disabled"] is True:
                suppression_reasons["disabled"] += 1
                eligibility["invalid"] += 1
                expected_conflicts.append(
                    {
                        "reason": "current_disabled",
                        "githubRepositoryId": repository_id,
                        "repository": current["repository"],
                        "currentStars": current["totalStars"],
                        "baselineStars": first["totalStars"],
                        "sourceCaptureIds": capture_ids,
                    }
                )
                continue
            delta = int(current["totalStars"]) - int(first["totalStars"])
            if delta < 0:
                suppression_reasons["negative_growth"] += 1
                eligibility["invalid"] += 1
                expected_conflicts.append(
                    {
                        "reason": "star_count_decreased",
                        "githubRepositoryId": repository_id,
                        "repository": current["repository"],
                        "currentStars": current["totalStars"],
                        "baselineStars": first["totalStars"],
                        "sourceCaptureIds": capture_ids,
                    }
                )
                continue
            if repository_id in published_ids:
                eligibility["todayPublished"] += 1
                suppression_reasons["today_published"] += 1
                continue
            eligibility_class = "exact_outside_published" if repository_id in exact_by_id else "pre_exact"
            eligibility["exactOutsidePublished" if repository_id in exact_by_id else "preExact"] += 1
            candidate_facts[repository_id] = {
                "current": current,
                "observations": observations,
                "delta": delta,
                "eligibilityClass": eligibility_class,
            }
        expected_conflicts.sort(key=lambda item: (item["reason"], item["repository"], item["githubRepositoryId"]))
        if artifact["conflicts"] != expected_conflicts:
            raise RardarArtifactError("rardar_discover_invalid", "Rardar Discover v3 conflicts are inconsistent")

        source_projects: dict[int, DiscoverSourceProject] = {}
        published_ids_seen: set[int] = set()
        published_outside = 0
        for stage, key in _STAGE_KEYS.items():
            raw_items = artifact["stages"][key]
            if raw_items != sorted(
                raw_items,
                key=lambda item: (-item["observedStarDelta"], -item["totalStars"], item["repository"]),
            ):
                raise RardarArtifactError("rardar_discover_invalid", "Rardar Discover v3 order is inconsistent")
            for raw_item in raw_items:
                repository_id = int(raw_item["githubRepositoryId"])
                if repository_id in published_ids_seen or repository_id not in candidate_facts:
                    raise RardarArtifactError("rardar_discover_invalid", "Rardar Discover v3 identity partition failed")
                facts = candidate_facts[repository_id]
                current = facts["current"]
                observations = facts["observations"]
                first_source, first = observations[0]
                delta = facts["delta"]
                hours = round(
                    (_timestamp(latest["capturedAt"]) - _timestamp(first_source["capturedAt"])).total_seconds() / 3600,
                    6,
                )
                consecutive = self._consecutive_capture_count(repository_id, payloads, indexes)
                consecutive_start = payloads[len(payloads) - consecutive]
                consecutive_hours = (
                    _timestamp(latest["capturedAt"]) - _timestamp(consecutive_start["capturedAt"])
                ).total_seconds() / 3600
                positive_count, longest_run, latest_delta = self._positive_interval_facts(observations)
                relative = round(delta / int(first["totalStars"]) * 100, 6) if int(first["totalStars"]) > 0 else None
                recent_delta, prior_delta, acceleration, recent_relative, recent_continuous = (
                    self._comparable_window_facts(observations, latest_scheduled_at=_timestamp(latest["scheduledAt"]))
                )
                exact = exact_by_id.get(repository_id)
                if facts["eligibilityClass"] == "exact_outside_published":
                    recent_absolute = recent_delta is not None and recent_delta >= 10
                    recent_relative_gate = recent_relative is not None and recent_relative >= 1.0
                    valid = (
                        stage == "outside_today_momentum"
                        and exact is not None
                        and int(exact["rank"]) > 20
                        and (recent_absolute or recent_relative_gate)
                        and recent_continuous >= 2
                        and acceleration is not None
                        and acceleration > 0
                    )
                    reasons = {
                        "outside_today_top20",
                        "exact_rank_available",
                        "continuous_recent_growth",
                        "recent_acceleration",
                    }
                    if recent_absolute:
                        reasons.add("recent_absolute_growth")
                    if recent_relative_gate:
                        reasons.add("recent_relative_growth")
                    published_outside += 1
                else:
                    recent = _timestamp(latest["scheduledAt"]) - _timestamp(first_source["scheduledAt"]) <= timedelta(
                        hours=4
                    )
                    absolute_gate = delta >= 10
                    relative_gate = relative is not None and relative >= 1.0
                    continuous_gate = longest_run >= 2
                    quality_gate = (absolute_gate or relative_gate) and continuous_gate
                    rising = len(observations) >= 3 and hours > 0 and delta > 0
                    expected_stage = (
                        "just_discovered"
                        if recent
                        else "near_validation"
                        if consecutive_hours >= 20 and quality_gate
                        else "rising"
                        if rising and quality_gate
                        else None
                    )
                    valid = stage == expected_stage and exact is None
                    reasons = {"first_seen_recently"} if recent else {"continuous_positive_growth"}
                    if not recent:
                        if absolute_gate:
                            reasons.add("absolute_growth_gate")
                        if relative_gate:
                            reasons.add("relative_growth_gate")
                        if expected_stage == "near_validation":
                            reasons.add("awaiting_today_settlement")
                ordered_reasons = self._ordered_signal_facts(reasons)
                expected_item = {
                    "githubRepositoryId": repository_id,
                    "repository": current["repository"],
                    "url": current["htmlUrl"],
                    "stage": stage,
                    "firstSeenAt": first_source["capturedAt"],
                    "lastObservedAt": latest["capturedAt"],
                    "observedWindowStart": first_source["capturedAt"],
                    "observedWindowEnd": latest["capturedAt"],
                    "observedWindowHours": hours,
                    "observedStarDelta": delta,
                    "totalStars": current["totalStars"],
                    "captureCount": len(observations),
                    "consecutiveCaptureCount": consecutive,
                    "language": current["primaryLanguage"],
                    "topics": copy.deepcopy(current["topics"]),
                    "license": current["licenseSpdxId"],
                    "isFork": current["fork"],
                    "isArchived": current["archived"],
                    "isDisabled": False,
                    "latestPushAt": current["pushedAt"],
                    "sourceCaptureIds": [source["captureId"] for source, _ in observations],
                    "sourceEvidenceDigest": self._evidence_digest(observations),
                    "relativeGrowthPercent": relative,
                    "positiveIntervalCount": positive_count,
                    "consecutivePositiveIntervalCount": longest_run,
                    "latestIntervalDelta": latest_delta,
                    "publishReasonCodes": ordered_reasons,
                    "signalFacts": ordered_reasons,
                    "eligibilityClass": facts["eligibilityClass"],
                    "todayExactRank": int(exact["rank"]) if exact is not None else None,
                    "todayExact24hDelta": int(exact["observedStarDelta"]) if exact is not None else None,
                    "recentWindowHours": min(4, hours),
                    "recentObservedStarDelta": recent_delta,
                    "priorComparableWindowDelta": prior_delta,
                    "accelerationDelta": acceleration,
                    "recentRelativeGrowthPercent": recent_relative,
                }
                if not valid or raw_item != expected_item:
                    raise RardarArtifactError(
                        "rardar_discover_invalid", "Rardar Discover v3 published proof is inconsistent"
                    )
                item = DiscoverItem.model_validate_json(json.dumps(raw_item), strict=True)
                source_projects[repository_id] = DiscoverSourceProject(
                    item=item,
                    description=current.get("description"),
                    forks=int(current.get("forks", 0)),
                    default_branch=str(current.get("defaultBranch") or "main"),
                )
                published_ids_seen.add(repository_id)

        for repository_id, facts in candidate_facts.items():
            if repository_id in published_ids_seen:
                continue
            observations = facts["observations"]
            if facts["eligibilityClass"] == "exact_outside_published":
                recent_delta, prior_delta, acceleration, recent_relative, recent_continuous = (
                    self._comparable_window_facts(observations, latest_scheduled_at=_timestamp(latest["scheduledAt"]))
                )
                suppression_reasons["already_exact_without_momentum"] += 1
                if recent_delta is None or recent_delta < 10:
                    suppression_reasons["weak_recent_absolute_growth"] += 1
                if recent_relative is None or recent_relative < 1.0:
                    suppression_reasons["weak_recent_relative_growth"] += 1
                if recent_continuous < 2:
                    suppression_reasons["no_recent_continuous_growth"] += 1
                if acceleration is None or acceleration <= 0:
                    suppression_reasons["no_recent_acceleration"] += 1
            else:
                suppression_reasons["weak_pre_exact_growth"] += 1

        coverage = artifact["coverage"]
        expected_coverage = {
            "state": "degraded" if any(payload["coverageState"] == "degraded" for payload in payloads) else "healthy",
            "querySuccessCount": latest["successfulQueryCount"],
            "queryFailureCount": latest["failedQueryCount"],
            "metadataFailureCount": latest["metadataFailureCount"],
            "sourceCaptureCount": len(payloads),
            "candidateCount": len(latest_index),
            "publishedCount": len(published_ids_seen),
            "conflictCount": len(expected_conflicts),
            "todayExactCount": len(exact_by_id),
            "todayPublishedCount": len(published_ids),
            "excludedPublishedCount": eligibility["todayPublished"],
            "exactOutsidePublishedEvaluatedCount": eligibility["exactOutsidePublished"],
            "preExactEvaluatedCount": eligibility["preExact"],
            "invalidCount": eligibility["invalid"],
        }
        expected_summary = {
            "candidateCount": len(latest_index),
            "publishedCount": len(published_ids_seen),
            "suppressedSignalCount": len(candidate_facts) - len(published_ids_seen),
            "excludedPublishedCount": eligibility["todayPublished"],
            "conflictCount": len(expected_conflicts),
            "reasons": suppression_reasons,
        }
        if (
            coverage != expected_coverage
            or artifact["eligibilityCounts"] != eligibility
            or artifact["excludedPublishedCount"] != eligibility["todayPublished"]
            or artifact["exactOutsidePublishedEvaluatedCount"] != eligibility["exactOutsidePublished"]
            or artifact["preExactEvaluatedCount"] != eligibility["preExact"]
            or artifact["suppressionSummary"] != expected_summary
            or published_outside != len(artifact["stages"]["outsideTodayMomentum"])
        ):
            raise RardarArtifactError("rardar_discover_invalid", "Rardar Discover v3 eligibility audit is inconsistent")
        return source_projects

    def _rebuild_v1(
        self,
        artifact: dict[str, Any],
        captures: list[tuple[dict[str, Any], bytes, dict[str, Any]]],
        today_source: tuple[dict[str, Any], bytes, dict[str, Any]],
    ) -> tuple[dict[str, Any], dict[int, DiscoverSourceProject]]:
        payloads = [entry[0] for entry in captures]
        indexes = [self._observation_index(payload) for payload in payloads]
        latest = payloads[-1]
        latest_index = indexes[-1]
        today, today_raw, today_reference = today_source
        exact_ids = {int(item["githubRepositoryId"]) for item in today["exactRanked"]}
        name_ids: dict[str, set[int]] = {}
        for index in indexes:
            for repository_id, item in index.items():
                name_ids.setdefault(str(item["repository"]).casefold(), set()).add(repository_id)
        stages: dict[str, list[dict[str, Any]]] = {value: [] for value in _LEGACY_STAGE_KEYS.values()}
        conflicts: list[dict[str, Any]] = []
        excluded_exact = 0
        source_projects: dict[int, DiscoverSourceProject] = {}
        for repository_id, current in latest_index.items():
            observations = [
                (payload, index[repository_id])
                for payload, index in zip(payloads, indexes, strict=True)
                if repository_id in index
            ]
            first_source, first = observations[0]
            capture_ids = [source["captureId"] for source, _ in observations]
            identity_conflict = any(len(name_ids[str(item["repository"]).casefold()]) != 1 for _, item in observations)
            if identity_conflict:
                conflicts.append(
                    {
                        "reason": "source_identity_conflict",
                        "githubRepositoryId": repository_id,
                        "repository": current["repository"],
                        "currentStars": current["totalStars"],
                        "baselineStars": first["totalStars"],
                        "sourceCaptureIds": capture_ids,
                    }
                )
                continue
            if current["disabled"] is True:
                conflicts.append(
                    {
                        "reason": "current_disabled",
                        "githubRepositoryId": repository_id,
                        "repository": current["repository"],
                        "currentStars": current["totalStars"],
                        "baselineStars": first["totalStars"],
                        "sourceCaptureIds": capture_ids,
                    }
                )
                continue
            if repository_id in exact_ids:
                excluded_exact += 1
                continue
            delta = int(current["totalStars"]) - int(first["totalStars"])
            if delta < 0:
                conflicts.append(
                    {
                        "reason": "star_count_decreased",
                        "githubRepositoryId": repository_id,
                        "repository": current["repository"],
                        "currentStars": current["totalStars"],
                        "baselineStars": first["totalStars"],
                        "sourceCaptureIds": capture_ids,
                    }
                )
                continue
            first_index = payloads.index(first_source)
            hours = round(
                (_timestamp(latest["capturedAt"]) - _timestamp(first_source["capturedAt"])).total_seconds() / 3600, 6
            )
            if hours < 0 or hours > 27:
                raise RardarArtifactError("rardar_discover_invalid", "Rardar Discover observation window is invalid")
            consecutive = 0
            previous: datetime | None = None
            for payload, index in reversed(list(zip(payloads, indexes, strict=True))):
                if repository_id not in index:
                    break
                scheduled = _timestamp(payload["scheduledAt"])
                if previous is not None and previous - scheduled != timedelta(minutes=120):
                    break
                consecutive += 1
                previous = scheduled
            consecutive_start = payloads[len(payloads) - consecutive]
            consecutive_hours = (
                _timestamp(latest["capturedAt"]) - _timestamp(consecutive_start["capturedAt"])
            ).total_seconds() / 3600
            near_validation = consecutive_hours >= 20
            just_discovered = first_index >= max(0, len(payloads) - 2) or hours <= 4
            rising = len(observations) >= 2 and hours > 0 and delta > 0
            stage = (
                "near_validation"
                if near_validation
                else "just_discovered"
                if just_discovered
                else "rising"
                if rising
                else None
            )
            if stage is None:
                continue
            item = {
                "githubRepositoryId": repository_id,
                "repository": current["repository"],
                "url": current["htmlUrl"],
                "stage": stage,
                "firstSeenAt": first_source["capturedAt"],
                "lastObservedAt": latest["capturedAt"],
                "observedWindowStart": first_source["capturedAt"],
                "observedWindowEnd": latest["capturedAt"],
                "observedWindowHours": hours,
                "observedStarDelta": delta,
                "totalStars": current["totalStars"],
                "captureCount": len(observations),
                "consecutiveCaptureCount": consecutive,
                "language": current["primaryLanguage"],
                "topics": copy.deepcopy(current["topics"]),
                "license": current["licenseSpdxId"],
                "isFork": current["fork"],
                "isArchived": current["archived"],
                "isDisabled": False,
                "latestPushAt": current["pushedAt"],
                "sourceCaptureIds": capture_ids,
                "sourceEvidenceDigest": self._evidence_digest(observations),
            }
            stages[_LEGACY_STAGE_KEYS[stage]].append(item)
        for values in stages.values():
            values.sort(key=lambda item: (-item["observedStarDelta"], -item["totalStars"], item["repository"]))
        conflicts.sort(key=lambda item: (item["reason"], item["repository"], item["githubRepositoryId"]))
        published_count = sum(len(values) for values in stages.values())
        expected = {
            "schemaVersion": 1,
            "policyVersion": "trending-discover-v1",
            "discoverGenerationId": artifact["discoverGenerationId"],
            "generatedAt": artifact["generatedAt"],
            "latestCaptureId": latest["captureId"],
            "latestCaptureScheduledAt": latest["scheduledAt"],
            "latestCaptureCapturedAt": latest["capturedAt"],
            "sourceWindowStart": payloads[0]["capturedAt"],
            "sourceWindowEnd": latest["capturedAt"],
            "sourceCaptureCount": len(payloads),
            "todayExplosionGenerationId": today_reference["generationId"],
            "todayExplosionDigest": _sha(today_raw),
            "updateCadenceMinutes": 120,
            "sortingPolicy": {
                "sections": list(_LEGACY_STAGE_SECTIONS),
                "withinStage": ["observedStarDelta DESC", "totalStars DESC", "repository ASC"],
            },
            "stages": stages,
            "coverage": {
                "state": "degraded"
                if any(payload["coverageState"] == "degraded" for payload in payloads)
                else "healthy",
                "querySuccessCount": latest["successfulQueryCount"],
                "queryFailureCount": latest["failedQueryCount"],
                "metadataFailureCount": latest["metadataFailureCount"],
                "sourceCaptureCount": len(payloads),
                "candidateCount": len(latest_index),
                "publishedCount": published_count,
                "conflictCount": len(conflicts),
                "excludedExactCount": excluded_exact,
            },
            "conflicts": conflicts,
            "sourceInventory": copy.deepcopy(artifact["sourceInventory"]),
            "todayExplosionSource": copy.deepcopy(artifact["todayExplosionSource"]),
        }
        expected["payloadDigest"] = {"algorithm": "sha256", "value": _payload_digest(expected)}
        for key in _LEGACY_STAGE_KEYS.values():
            for raw_item in stages[key]:
                item = DiscoverItem.model_validate_json(json.dumps(raw_item), strict=True)
                current = latest_index[item.githubRepositoryId]
                source_projects[item.githubRepositoryId] = DiscoverSourceProject(
                    item=item,
                    description=current.get("description"),
                    forks=int(current.get("forks", 0)),
                    default_branch=str(current.get("defaultBranch") or "main"),
                )
        return expected, source_projects

    @staticmethod
    def _project_board(artifact: dict[str, Any]) -> DiscoverBoard:
        reasons: dict[str, int] = {}
        for conflict in artifact["conflicts"]:
            reasons[conflict["reason"]] = reasons.get(conflict["reason"], 0) + 1
        payload = {
            "schemaVersion": artifact["schemaVersion"],
            "policyVersion": artifact["policyVersion"],
            "discoverGenerationId": artifact["discoverGenerationId"],
            "generatedAt": artifact["generatedAt"],
            "latestCaptureId": artifact["latestCaptureId"],
            "latestCaptureScheduledAt": artifact["latestCaptureScheduledAt"],
            "latestCaptureCapturedAt": artifact["latestCaptureCapturedAt"],
            "sourceWindowStart": artifact["sourceWindowStart"],
            "sourceWindowEnd": artifact["sourceWindowEnd"],
            "sourceCaptureCount": artifact["sourceCaptureCount"],
            "todayExplosionGenerationId": artifact["todayExplosionGenerationId"],
            "todayExplosionDigest": artifact["todayExplosionDigest"],
            "updateCadenceMinutes": artifact["updateCadenceMinutes"],
            "justDiscovered": artifact["stages"]["justDiscovered"],
            "outsideTodayMomentum": artifact["stages"].get("outsideTodayMomentum", []),
            "rising": artifact["stages"]["rising"],
            "nearValidation": artifact["stages"]["nearValidation"],
            "coverage": artifact["coverage"],
            "conflictCount": len(artifact["conflicts"]),
            "conflictReasons": reasons,
            "stageCounts": {
                "justDiscovered": len(artifact["stages"]["justDiscovered"]),
                "outsideTodayMomentum": len(artifact["stages"].get("outsideTodayMomentum", [])),
                "rising": len(artifact["stages"]["rising"]),
                "nearValidation": len(artifact["stages"]["nearValidation"]),
            },
            "signalPolicy": artifact.get("signalPolicy"),
            "suppressionSummary": artifact.get("suppressionSummary"),
            "todayExactCount": artifact.get("todayExactCount"),
            "todayPublishedTopCount": artifact.get("todayPublishedTopCount"),
            "todayPublishedCount": artifact.get("todayPublishedCount"),
            "todayPublishedSetDigest": artifact.get("todayPublishedSetDigest"),
            "excludedPublishedCount": artifact.get("excludedPublishedCount"),
            "exactOutsidePublishedEvaluatedCount": artifact.get("exactOutsidePublishedEvaluatedCount"),
            "preExactEvaluatedCount": artifact.get("preExactEvaluatedCount"),
            "eligibilityCounts": artifact.get("eligibilityCounts"),
            "payloadDigest": artifact["payloadDigest"]["value"],
        }
        return DiscoverBoard.model_validate_json(json.dumps(payload), strict=True)


__all__ = [
    "DISCOVER_ROOT",
    "DiscoverArtifactAdapter",
    "DiscoverBoard",
    "DiscoverCoverage",
    "DiscoverItem",
    "DiscoverSignalPolicy",
    "DiscoverSuppressionSummaryV3",
    "DiscoverSourceProject",
    "LoadedDiscoverArtifact",
]
