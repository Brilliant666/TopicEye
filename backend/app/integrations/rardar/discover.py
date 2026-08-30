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

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl

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
_STAGE_KEYS = {
    "just_discovered": "justDiscovered",
    "rising": "rising",
    "near_validation": "nearValidation",
}
_STAGE_SECTIONS = ("just_discovered", "rising", "near_validation")


class StrictDiscoverModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class DiscoverItem(StrictDiscoverModel):
    githubRepositoryId: int = Field(gt=0)
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    url: HttpUrl
    stage: Literal["just_discovered", "rising", "near_validation"]
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


class DiscoverCoverage(StrictDiscoverModel):
    state: Literal["healthy", "degraded"]
    querySuccessCount: int = Field(ge=1, le=9)
    queryFailureCount: int = Field(ge=0, le=8)
    metadataFailureCount: int = Field(ge=0, le=500)
    sourceCaptureCount: int = Field(ge=1, le=14)
    candidateCount: int = Field(ge=0, le=500)
    publishedCount: int = Field(ge=0, le=500)
    conflictCount: int = Field(ge=0, le=500)
    excludedExactCount: int = Field(ge=0, le=500)


class DiscoverStageCounts(StrictDiscoverModel):
    justDiscovered: int = Field(ge=0, le=500)
    rising: int = Field(ge=0, le=500)
    nearValidation: int = Field(ge=0, le=500)


class DiscoverBoard(StrictDiscoverModel):
    schemaVersion: Literal[1]
    policyVersion: Literal["trending-discover-v1"]
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
    rising: list[DiscoverItem] = Field(max_length=500)
    nearValidation: list[DiscoverItem] = Field(max_length=500)
    coverage: DiscoverCoverage
    conflictCount: int = Field(ge=0, le=500)
    conflictReasons: dict[str, int]
    stageCounts: DiscoverStageCounts
    payloadDigest: str = Field(pattern=r"^[a-f0-9]{64}$")


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
        ):
            raise RardarArtifactError("rardar_discover_invalid", "Rardar Discover payload binding is invalid")

        captures = self._load_captures(base, artifact, manifest)
        today = self._load_today(base, artifact, manifest)
        rebuilt, source_projects = self._rebuild(artifact, captures, today)
        if rebuilt != artifact:
            raise RardarArtifactError("rardar_discover_invalid", "Rardar Discover source recomputation failed")
        expected_audit = {
            "status": artifact["coverage"]["state"],
            "validatedSourceCount": artifact["sourceCaptureCount"] + 1,
            "publishedCount": artifact["coverage"]["publishedCount"],
            "conflictCount": artifact["coverage"]["conflictCount"],
        }
        if manifest["audit"] != expected_audit:
            raise RardarArtifactError("rardar_discover_invalid", "Rardar Discover manifest audit is inconsistent")
        board = self._project_board(artifact)
        return LoadedDiscoverArtifact(
            board=board,
            pointer_raw=pointer_raw,
            manifest_sha256=_sha(manifest_raw),
            artifact_sha256=_sha(artifact_raw),
            projects=source_projects,
        )

    def _load_captures(
        self, base: str, artifact: dict[str, Any], manifest: dict[str, Any]
    ) -> list[tuple[dict[str, Any], bytes, dict[str, Any]]]:
        captures: list[tuple[dict[str, Any], bytes, dict[str, Any]]] = []
        previous: datetime | None = None
        for reference in artifact["sourceInventory"]:
            relative = reference["generationRelativePath"]
            payload, raw = self._json(f"{base}/{relative}", 16 * 1024 * 1024, "source capture")
            self._schema("trending-capture-bundle.schema.json", payload, "source capture")
            if (
                manifest["artifacts"].get(relative) != _sha(raw)
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

    def _rebuild(
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
        stages: dict[str, list[dict[str, Any]]] = {value: [] for value in _STAGE_KEYS.values()}
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
            stages[_STAGE_KEYS[stage]].append(item)
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
                "sections": list(_STAGE_SECTIONS),
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
        for key in _STAGE_KEYS.values():
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
            "rising": artifact["stages"]["rising"],
            "nearValidation": artifact["stages"]["nearValidation"],
            "coverage": artifact["coverage"],
            "conflictCount": len(artifact["conflicts"]),
            "conflictReasons": reasons,
            "stageCounts": {
                "justDiscovered": len(artifact["stages"]["justDiscovered"]),
                "rising": len(artifact["stages"]["rising"]),
                "nearValidation": len(artifact["stages"]["nearValidation"]),
            },
            "payloadDigest": artifact["payloadDigest"]["value"],
        }
        return DiscoverBoard.model_validate_json(json.dumps(payload), strict=True)


__all__ = [
    "DISCOVER_ROOT",
    "DiscoverArtifactAdapter",
    "DiscoverBoard",
    "DiscoverCoverage",
    "DiscoverItem",
    "DiscoverSourceProject",
    "LoadedDiscoverArtifact",
]
