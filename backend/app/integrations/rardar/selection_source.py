"""Read-only synchronization and fail-closed loading for Selection facts.

The source mirror deliberately does not depend on Rardar's optional Discover
publication.  It binds one continuous Observation window to one authoritative
Today generation, then publishes that bounded fact bundle atomically outside
the repository.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from jsonschema.exceptions import ValidationError as JSONSchemaValidationError
from pydantic import BaseModel, ValidationError
from pydantic_core import to_jsonable_python

from app.integrations.rardar.adapter import (
    RardarArtifactError,
    _capture_payload_digest,
    _SafeRoot,
    _strict_json,
    _validate,
)
from app.integrations.rardar.selection_schemas import (
    SelectionSourceFile,
    SelectionSourceManifest,
    SelectionSourcePointer,
)

SELECTION_SOURCE_ROOT = "selection-source"
_CAPTURE_ID = re.compile(r"^trending-v1-([0-9]{8}T[0-9]{6}Z)$")
_GENERATION_ID = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,188}[A-Za-z0-9])?$")
_HOST = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
_REPARSE_POINT = 0x400
_MAX_BUNDLE = 256 * 1024 * 1024
_MAX_SOURCE_CAPTURES = 37
_MIN_SOURCE_CAPTURES = 2


class SelectionSourceError(RardarArtifactError):
    """Stable Selection source error without host paths or source content."""


@dataclass(frozen=True)
class LoadedSelectionSource:
    source_observation_set_id: str
    pointer_raw: bytes
    manifest_sha256: str
    inventory_digest: str
    captures: tuple[dict[str, Any], ...]
    today: dict[str, Any]
    latest_capture_id: str
    latest_capture_at: str
    source_window_start: str
    source_window_end: str
    today_generation_id: str
    today_explosion_sha256: str
    today_published_set_digest: str
    source_coverage_state: str


@dataclass(frozen=True)
class BuiltSelectionSource:
    source_observation_set_id: str
    manifest_sha256: str
    pointer_raw: bytes
    files: dict[str, bytes]


@dataclass(frozen=True)
class SelectionSourceInstallResult:
    source_observation_set_id: str
    manifest_sha256: str
    capture_count: int
    today_generation_id: str
    created: bool
    changed: bool


def _canonical_bytes(value: object) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return (
        json.dumps(
            to_jsonable_python(value),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp has no timezone")
    return parsed.astimezone(UTC)


def _strict_model(raw: bytes, model: type[Any]) -> Any:
    try:
        return model.model_validate_json(raw, strict=True)
    except (ValidationError, ValueError) as exc:
        raise SelectionSourceError("rardar_selection_source_invalid", "Selection source contract is invalid") from exc


def _safe_relative(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value or value.startswith("/"):
        raise SelectionSourceError("rardar_selection_source_invalid", "Selection source path is unsafe")
    if any(part in {"", ".", ".."} for part in value.split("/")):
        raise SelectionSourceError("rardar_selection_source_invalid", "Selection source path is unsafe")
    return value


def _decode(value: object, *, maximum: int = 16 * 1024 * 1024) -> bytes:
    if not isinstance(value, str):
        raise SelectionSourceError("rardar_selection_source_invalid", "Selection source bundle is invalid")
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise SelectionSourceError("rardar_selection_source_invalid", "Selection source bundle is invalid") from exc
    if not raw or len(raw) > maximum:
        raise SelectionSourceError("rardar_selection_source_invalid", "Selection source file size is invalid")
    return raw


def _schema(name: str, value: dict[str, Any], label: str) -> None:
    try:
        _validate(name, value)
    except (JSONSchemaValidationError, ValueError) as exc:
        raise SelectionSourceError(
            "rardar_selection_source_invalid", f"Selection source {label} failed Schema validation"
        ) from exc


def _capture(raw: bytes, expected_id: str | None = None) -> dict[str, Any]:
    try:
        value = _strict_json(raw)
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise SelectionSourceError("rardar_selection_source_invalid", "Observation capture JSON is invalid") from exc
    _schema("trending-capture-bundle.schema.json", value, "Observation capture")
    capture_id = value["captureId"]
    match = _CAPTURE_ID.fullmatch(capture_id)
    if match is None or (expected_id is not None and capture_id != expected_id):
        raise SelectionSourceError("rardar_selection_source_invalid", "Observation capture identity is invalid")
    scheduled = _timestamp(value["scheduledAt"])
    filename_time = datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    if (
        scheduled != filename_time
        or value["windowEligible"] is not True
        or value["cadenceMinutes"] != 120
        or _capture_payload_digest(value) != value["digest"]["value"]
    ):
        raise SelectionSourceError("rardar_selection_source_invalid", "Observation capture provenance is invalid")
    return value


def _today_references(explosion: dict[str, Any]) -> list[dict[str, Any]]:
    captures = explosion["sourceCaptures"]
    references = [captures["current"]]
    if captures["baseline"] is not None:
        references.append(captures["baseline"])
    references.extend(captures["partial"])
    if captures["coverageWitness"] is not None:
        references.append(captures["coverageWitness"])
    return references


def _validate_today(files: dict[str, bytes]) -> tuple[dict[str, Any], str, str, str, dict[str, str]]:
    required = {"today/current.json", "today/manifest.json", "today/explosion.json"}
    if not required.issubset(files):
        raise SelectionSourceError("rardar_selection_source_invalid", "Today source inventory is incomplete")
    try:
        pointer = _strict_json(files["today/current.json"])
        manifest = _strict_json(files["today/manifest.json"])
        explosion = _strict_json(files["today/explosion.json"])
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise SelectionSourceError("rardar_selection_source_invalid", "Today source JSON is invalid") from exc
    _schema("current-generation.schema.json", pointer, "Today pointer")
    _schema("generation-manifest.schema.json", manifest, "Today manifest")
    _schema("trending-explosion-artifact.schema.json", explosion, "Today Explosion")
    generation = pointer["generationId"]
    if (
        not _GENERATION_ID.fullmatch(generation)
        or pointer["manifestSha256"] != _sha(files["today/manifest.json"])
        or manifest["generationId"] != generation
        or manifest["state"] != "ready"
        or explosion["generationId"] != generation
        or "trending/explosion.json" not in manifest["hashes"]
        or manifest["hashes"]["trending/explosion.json"] != _sha(files["today/explosion.json"])
    ):
        raise SelectionSourceError("rardar_selection_source_invalid", "Today generation binding is invalid")

    paths: set[str] = set()
    source_by_path: dict[str, dict[str, Any]] = {}
    source_digests: dict[str, str] = {}
    for reference in _today_references(explosion):
        relative = _safe_relative(reference["generationRelativePath"])
        if relative in paths:
            raise SelectionSourceError("rardar_selection_source_invalid", "Today source paths are duplicated")
        paths.add(relative)
        key = f"today/generation/{relative}"
        if key not in files or relative not in manifest["hashes"]:
            raise SelectionSourceError("rardar_selection_source_invalid", "Today source copy is missing")
        raw = files[key]
        if _sha(raw) not in {manifest["hashes"][relative], reference["fileSha256"]} or (
            manifest["hashes"][relative] != reference["fileSha256"]
        ):
            raise SelectionSourceError("rardar_selection_source_invalid", "Today source digest is invalid")
        value = _capture(raw, reference["captureId"])
        if (
            any(
                value[field] != reference[field]
                for field in ("captureId", "scheduledAt", "capturedAt", "coverageState")
            )
            or value["digest"]["value"] != reference["payloadDigestSha256"]
        ):
            raise SelectionSourceError("rardar_selection_source_invalid", "Today source provenance is inconsistent")
        source_by_path[relative] = value
        source_digests[value["captureId"]] = _sha(raw)

    exact = explosion["exactRanked"]
    pending = explosion["pendingRanked"]
    conflicts = explosion["conflicts"]
    if [item["rank"] for item in exact] != list(range(1, len(exact) + 1)) or exact != sorted(
        exact, key=lambda item: (-item["observedStarDelta"], -item["totalStars"], item["repository"])
    ):
        raise SelectionSourceError("rardar_selection_source_invalid", "Today exact ranking is invalid")
    if [item["pendingRank"] for item in pending] != list(range(1, len(pending) + 1)):
        raise SelectionSourceError("rardar_selection_source_invalid", "Today pending ranking is invalid")
    identities = [item["githubRepositoryId"] for group in (exact, pending, conflicts) for item in group]
    if len(identities) != len(set(identities)):
        raise SelectionSourceError("rardar_selection_source_invalid", "Today ranking partitions overlap")
    current_ref = explosion["sourceCaptures"]["current"]
    current = source_by_path[current_ref["generationRelativePath"]]
    observations = {item["githubRepositoryId"]: item for item in current["observations"]}
    if len(observations) != len(current["observations"]):
        raise SelectionSourceError("rardar_selection_source_invalid", "Today observations contain duplicate identities")
    for item in (*exact, *pending):
        observed = observations.get(item["githubRepositoryId"])
        if observed is None or any(
            observed[field] != item[field]
            for field in ("repository", "htmlUrl", "totalStars", "primaryLanguage", "topics")
        ):
            raise SelectionSourceError("rardar_selection_source_invalid", "Today ranking does not match its source")
    top20 = sorted(int(item["githubRepositoryId"]) for item in exact if int(item["rank"]) <= 20)
    top20_digest = _sha(_canonical_bytes({"githubRepositoryIds": top20}))
    return explosion, generation, _sha(files["today/explosion.json"]), top20_digest, source_digests


def _validate_facts(files: dict[str, bytes]) -> dict[str, Any]:
    capture_pairs: list[tuple[datetime, dict[str, Any]]] = []
    for path, raw in files.items():
        if not path.startswith("captures/"):
            continue
        name = path.removeprefix("captures/").removesuffix(".json")
        if path != f"captures/{name}.json":
            raise SelectionSourceError("rardar_selection_source_invalid", "Observation path is invalid")
        value = _capture(raw, name)
        capture_pairs.append((_timestamp(value["scheduledAt"]), value))
    capture_pairs.sort(key=lambda item: item[0])
    if not _MIN_SOURCE_CAPTURES <= len(capture_pairs) <= _MAX_SOURCE_CAPTURES:
        raise SelectionSourceError("rardar_selection_source_invalid", "Observation window size is invalid")
    if len({value["captureId"] for _at, value in capture_pairs}) != len(capture_pairs):
        raise SelectionSourceError("rardar_selection_source_invalid", "Observation identities are duplicated")
    phase_gaps = False
    for (previous, _), (current, _) in zip(capture_pairs, capture_pairs[1:], strict=False):
        gap = (current - previous).total_seconds()
        if gap <= 0 or gap % 7200 != 0:
            raise SelectionSourceError("rardar_selection_source_invalid", "Observation phases are not aligned")
        phase_gaps = phase_gaps or gap != 7200
    window_hours = (capture_pairs[-1][0] - capture_pairs[0][0]).total_seconds() / 3600
    if window_hours < 26 or window_hours > 72:
        raise SelectionSourceError("rardar_selection_source_invalid", "Observation window must cover 26 to 72 hours")

    today, generation, explosion_sha, top20_digest, today_capture_digests = _validate_today(files)
    latest = capture_pairs[-1][1]
    latest_scheduled = capture_pairs[-1][0]
    today_end = _timestamp(today["window"]["endedAt"])
    if today_end > latest_scheduled or latest_scheduled - today_end > timedelta(hours=72):
        raise SelectionSourceError(
            "rardar_selection_source_invalid", "Today and Observation revisions are inconsistent"
        )
    coverage_state = (
        "healthy"
        if not phase_gaps
        and all(value["coverageState"] == "healthy" for _at, value in capture_pairs)
        and today["coverage"]["state"] == "healthy"
        else "degraded"
    )
    captures = tuple(value for _at, value in capture_pairs)
    capture_digests = {value["captureId"]: _sha(files[f"captures/{value['captureId']}.json"]) for value in captures}
    for capture_id in set(capture_digests).intersection(today_capture_digests):
        if capture_digests[capture_id] != today_capture_digests[capture_id]:
            raise SelectionSourceError(
                "rardar_selection_source_invalid", "Today and Observation copies disagree for one capture"
            )
    identity_seed = {
        "sourceCaptureDigests": capture_digests,
        "todayGenerationId": generation,
        "todayManifestSha256": _sha(files["today/manifest.json"]),
        "todayExplosionSha256": explosion_sha,
        "todayPublishedSetDigest": top20_digest,
    }
    source_id = f"observation-v1-{_sha(_canonical_bytes(identity_seed))[:32]}"
    return {
        "source_id": source_id,
        "captures": captures,
        "today": today,
        "latest_capture_id": latest["captureId"],
        "latest_capture_at": latest["capturedAt"],
        "source_window_start": captures[0]["capturedAt"],
        "source_window_end": latest["capturedAt"],
        "source_coverage_state": coverage_state,
        "today_generation_id": generation,
        "today_explosion_sha256": explosion_sha,
        "today_published_set_digest": top20_digest,
        "capture_digests": capture_digests,
    }


def build_selection_source(remote_bundle: bytes) -> BuiltSelectionSource:
    if not remote_bundle or len(remote_bundle) > _MAX_BUNDLE:
        raise SelectionSourceError("rardar_selection_source_invalid", "Selection source bundle size is invalid")
    try:
        bundle = _strict_json(remote_bundle)
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise SelectionSourceError(
            "rardar_selection_source_invalid", "Selection source bundle JSON is invalid"
        ) from exc
    if bundle.get("schemaVersion") != 1 or set(bundle) != {"schemaVersion", "captures", "today"}:
        raise SelectionSourceError("rardar_selection_source_invalid", "Selection source bundle contract is invalid")
    captures = bundle["captures"]
    today = bundle["today"]
    if not isinstance(captures, list) or not isinstance(today, dict) or len(captures) > _MAX_SOURCE_CAPTURES:
        raise SelectionSourceError("rardar_selection_source_invalid", "Selection source bundle inventory is invalid")
    files: dict[str, bytes] = {}
    for item in captures:
        if not isinstance(item, dict) or set(item) != {"captureId", "content"}:
            raise SelectionSourceError("rardar_selection_source_invalid", "Observation bundle entry is invalid")
        capture_id = item["captureId"]
        if not isinstance(capture_id, str) or _CAPTURE_ID.fullmatch(capture_id) is None:
            raise SelectionSourceError("rardar_selection_source_invalid", "Observation bundle identity is invalid")
        key = f"captures/{capture_id}.json"
        if key in files:
            raise SelectionSourceError("rardar_selection_source_invalid", "Observation bundle identity is duplicated")
        files[key] = _decode(item["content"])
    if set(today) != {"current", "manifest", "explosion", "generationFiles"} or not isinstance(
        today["generationFiles"], dict
    ):
        raise SelectionSourceError("rardar_selection_source_invalid", "Today bundle entry is invalid")
    files["today/current.json"] = _decode(today["current"], maximum=64 * 1024)
    files["today/manifest.json"] = _decode(today["manifest"], maximum=4 * 1024 * 1024)
    files["today/explosion.json"] = _decode(today["explosion"])
    for relative, encoded in today["generationFiles"].items():
        safe = _safe_relative(relative)
        key = f"today/generation/{safe}"
        if key in files:
            raise SelectionSourceError("rardar_selection_source_invalid", "Today bundle path is duplicated")
        files[key] = _decode(encoded)

    facts = _validate_facts(files)
    inventory = [
        SelectionSourceFile(path=path, sha256=_sha(raw), bytes=len(raw)) for path, raw in sorted(files.items())
    ]
    inventory_digest = _sha(_canonical_bytes([item.model_dump(mode="json") for item in inventory]))
    manifest = SelectionSourceManifest(
        schemaVersion=1,
        state="ready",
        sourceObservationSetId=facts["source_id"],
        capturedAt=_timestamp(facts["latest_capture_at"]),
        latestCaptureId=facts["latest_capture_id"],
        latestCaptureAt=_timestamp(facts["latest_capture_at"]),
        sourceWindowStart=_timestamp(facts["source_window_start"]),
        sourceWindowEnd=_timestamp(facts["source_window_end"]),
        sourceCoverageState=facts["source_coverage_state"],
        todayGenerationId=facts["today_generation_id"],
        todayExplosionSha256=facts["today_explosion_sha256"],
        todayPublishedSetDigest=facts["today_published_set_digest"],
        captureIds=[value["captureId"] for value in facts["captures"]],
        files=inventory,
        inventoryDigest=inventory_digest,
    )
    manifest_raw = _canonical_bytes(manifest)
    files["manifest.json"] = manifest_raw
    pointer = SelectionSourcePointer(
        schemaVersion=1,
        sourceObservationSetId=facts["source_id"],
        manifestSha256=_sha(manifest_raw),
        activatedAt=_timestamp(facts["latest_capture_at"]),
    )
    return BuiltSelectionSource(
        source_observation_set_id=facts["source_id"],
        manifest_sha256=_sha(manifest_raw),
        pointer_raw=_canonical_bytes(pointer),
        files=files,
    )


def _is_reparse(info: os.stat_result) -> bool:
    return bool(getattr(info, "st_file_attributes", 0) & _REPARSE_POINT)


def _ensure_plain(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    info = os.lstat(path)
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or _is_reparse(info):
        raise SelectionSourceError("rardar_selection_source_unsafe_path", "Selection source path is unsafe")


def _optional_bytes(path: Path) -> bytes | None:
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode) or _is_reparse(info):
        raise SelectionSourceError("rardar_selection_source_unsafe_path", "Selection source pointer is unsafe")
    return path.read_bytes()


def _atomic(path: Path, raw: bytes) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        with suppress(FileNotFoundError):
            os.unlink(temporary)
        raise


class SelectionSourceAdapter:
    def __init__(self, target: Path | str) -> None:
        self.target = Path(target)
        self.safe = _SafeRoot(str(self.target))

    @classmethod
    def from_config(cls, configured: str) -> SelectionSourceAdapter:
        return cls(configured)

    def _read(self, relative: str, maximum: int) -> bytes:
        try:
            return self.safe.read_stable(relative, maximum_bytes=maximum)
        except (FileNotFoundError, OSError, ValueError) as exc:
            raise SelectionSourceError("rardar_selection_source_invalid", "Selection source read failed") from exc

    def _manifest(self, source_id: str, expected_sha: str) -> tuple[SelectionSourceManifest, bytes]:
        if _GENERATION_ID.fullmatch(source_id) is None:
            raise SelectionSourceError("rardar_selection_source_invalid", "Selection source identity is unsafe")
        raw = self._read(f"{SELECTION_SOURCE_ROOT}/generations/{source_id}/manifest.json", 1024 * 1024)
        if _sha(raw) != expected_sha:
            raise SelectionSourceError("rardar_selection_source_invalid", "Selection source manifest digest is invalid")
        manifest = _strict_model(raw, SelectionSourceManifest)
        if manifest.sourceObservationSetId != source_id or manifest.state != "ready":
            raise SelectionSourceError("rardar_selection_source_invalid", "Selection source manifest is mixed")
        return manifest, raw

    def load(self) -> LoadedSelectionSource:
        try:
            pointer_raw = self.safe.read_stable(f"{SELECTION_SOURCE_ROOT}/current.json", maximum_bytes=64 * 1024)
        except FileNotFoundError as exc:
            raise SelectionSourceError(
                "rardar_selection_source_not_configured", "Selection source is not synchronized"
            ) from exc
        pointer = _strict_model(pointer_raw, SelectionSourcePointer)
        source_id = pointer.sourceObservationSetId
        manifest, _manifest_raw = self._manifest(source_id, pointer.manifestSha256)
        descriptors = {item.path: item for item in manifest.files}
        if len(descriptors) != len(manifest.files):
            raise SelectionSourceError("rardar_selection_source_invalid", "Selection source inventory is duplicated")
        files: dict[str, bytes] = {}
        for path, descriptor in descriptors.items():
            raw = self._read(f"{SELECTION_SOURCE_ROOT}/generations/{source_id}/{path}", descriptor.bytes)
            if len(raw) != descriptor.bytes or _sha(raw) != descriptor.sha256:
                raise SelectionSourceError("rardar_selection_source_invalid", "Selection source file digest is invalid")
            files[path] = raw
        facts = _validate_facts(files)
        inventory_digest = _sha(_canonical_bytes([item.model_dump(mode="json") for item in manifest.files]))
        expected_paths = {"manifest.json", *descriptors}
        actual_paths: set[str] = set()
        root = self.target / SELECTION_SOURCE_ROOT / "generations" / source_id
        for path in root.rglob("*"):
            info = os.lstat(path)
            if stat.S_ISLNK(info.st_mode) or _is_reparse(info):
                raise SelectionSourceError("rardar_selection_source_unsafe_path", "Selection source is unsafe")
            if stat.S_ISREG(info.st_mode):
                actual_paths.add(path.relative_to(root).as_posix())
            elif not stat.S_ISDIR(info.st_mode):
                raise SelectionSourceError("rardar_selection_source_unsafe_path", "Selection source is unsafe")
        if (
            actual_paths != expected_paths
            or inventory_digest != manifest.inventoryDigest
            or facts["source_id"] != source_id
            or facts["latest_capture_id"] != manifest.latestCaptureId
            or _timestamp(facts["latest_capture_at"]) != manifest.latestCaptureAt
            or _timestamp(facts["source_window_start"]) != manifest.sourceWindowStart
            or _timestamp(facts["source_window_end"]) != manifest.sourceWindowEnd
            or facts["source_coverage_state"] != manifest.sourceCoverageState
            or facts["today_generation_id"] != manifest.todayGenerationId
            or facts["today_explosion_sha256"] != manifest.todayExplosionSha256
            or facts["today_published_set_digest"] != manifest.todayPublishedSetDigest
            or [item["captureId"] for item in facts["captures"]] != manifest.captureIds
        ):
            raise SelectionSourceError("rardar_selection_source_invalid", "Selection source cross-file audit failed")
        return LoadedSelectionSource(
            source_observation_set_id=source_id,
            pointer_raw=pointer_raw,
            manifest_sha256=pointer.manifestSha256,
            inventory_digest=manifest.inventoryDigest,
            captures=facts["captures"],
            today=facts["today"],
            latest_capture_id=facts["latest_capture_id"],
            latest_capture_at=facts["latest_capture_at"],
            source_window_start=facts["source_window_start"],
            source_window_end=facts["source_window_end"],
            today_generation_id=facts["today_generation_id"],
            today_explosion_sha256=facts["today_explosion_sha256"],
            today_published_set_digest=facts["today_published_set_digest"],
            source_coverage_state=facts["source_coverage_state"],
        )


def _tree_matches(root: Path, expected: dict[str, bytes]) -> bool:
    actual: set[str] = set()
    for path in root.rglob("*"):
        info = os.lstat(path)
        if stat.S_ISLNK(info.st_mode) or _is_reparse(info):
            raise SelectionSourceError("rardar_selection_source_unsafe_path", "Selection source generation is unsafe")
        if stat.S_ISREG(info.st_mode):
            actual.add(path.relative_to(root).as_posix())
        elif not stat.S_ISDIR(info.st_mode):
            raise SelectionSourceError("rardar_selection_source_unsafe_path", "Selection source generation is unsafe")
    if actual != set(expected):
        return False
    safe = _SafeRoot(str(root))
    return all(safe.read_stable(path, maximum_bytes=len(raw)) == raw for path, raw in expected.items())


def install_selection_source(target: Path, built: BuiltSelectionSource) -> SelectionSourceInstallResult:
    target = target.resolve()
    store = target / SELECTION_SOURCE_ROOT
    generations = store / "generations"
    _ensure_plain(target)
    _ensure_plain(store)
    _ensure_plain(generations)
    pointer_path = store / "current.json"
    previous = _optional_bytes(pointer_path)
    if previous == built.pointer_raw:
        loaded = SelectionSourceAdapter(target).load()
        if (
            loaded.source_observation_set_id != built.source_observation_set_id
            or loaded.manifest_sha256 != built.manifest_sha256
        ):
            raise SelectionSourceError("rardar_selection_source_invalid", "Active Selection source is mixed")
        return SelectionSourceInstallResult(
            loaded.source_observation_set_id,
            loaded.manifest_sha256,
            len(loaded.captures),
            loaded.today_generation_id,
            False,
            False,
        )
    final = generations / built.source_observation_set_id
    created = False
    if final.exists():
        _ensure_plain(final)
        if not _tree_matches(final, built.files):
            raise SelectionSourceError("rardar_selection_source_conflict", "Immutable Selection source differs")
    else:
        candidate = generations / f".{built.source_observation_set_id}.candidate-{os.getpid()}"
        if candidate.exists():
            raise SelectionSourceError("rardar_selection_source_conflict", "Selection source candidate exists")
        try:
            for relative, raw in built.files.items():
                path = candidate.joinpath(*relative.split("/"))
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            os.replace(candidate, final)
            created = True
        except Exception:
            shutil.rmtree(candidate, ignore_errors=True)
            raise
    try:
        # Validate the retained generation by using a temporary pointer only in
        # an isolated sibling root; the active pointer remains untouched.
        manifest = _strict_model(built.files["manifest.json"], SelectionSourceManifest)
        if manifest.sourceObservationSetId != built.source_observation_set_id:
            raise SelectionSourceError("rardar_selection_source_invalid", "Selection source identity is mixed")
        _validate_facts({key: value for key, value in built.files.items() if key != "manifest.json"})
    except Exception:
        if created:
            shutil.rmtree(final, ignore_errors=True)
        raise
    try:
        _atomic(pointer_path, built.pointer_raw)
        loaded = SelectionSourceAdapter(target).load()
        if loaded.source_observation_set_id != built.source_observation_set_id:
            raise SelectionSourceError("rardar_selection_source_activation_failed", "Selection source did not activate")
    except Exception:
        if previous is None:
            pointer_path.unlink(missing_ok=True)
        else:
            _atomic(pointer_path, previous)
        if created:
            shutil.rmtree(final, ignore_errors=True)
        raise
    return SelectionSourceInstallResult(
        loaded.source_observation_set_id,
        loaded.manifest_sha256,
        len(loaded.captures),
        loaded.today_generation_id,
        created,
        True,
    )


_REMOTE_PROGRAM = r"""
import base64, datetime, hashlib, json, os, re, stat, sys

ROOT = __REMOTE_ROOT__
CAPTURE = re.compile(r"^trending-v1-([0-9]{8}T[0-9]{6}Z)\.json$")
GENERATION = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,126}[A-Za-z0-9])?$")
MAX_FILE = 16 * 1024 * 1024

def safe_parts(relative):
    if not isinstance(relative, str) or not relative or "\\" in relative or relative.startswith("/"):
        raise RuntimeError("unsafe_path")
    parts = relative.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise RuntimeError("unsafe_path")
    return parts

def read_stable(relative, maximum=MAX_FILE):
    path = os.path.join(ROOT, *safe_parts(relative))
    before = os.lstat(path)
    if not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode) or before.st_size > maximum:
        raise RuntimeError("unsafe_file")
    with open(path, "rb") as handle:
        first = handle.read(maximum + 1)
    middle = os.lstat(path)
    with open(path, "rb") as handle:
        second = handle.read(maximum + 1)
    after = os.lstat(path)
    identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)
    if len(first) > maximum or first != second or identity(before) != identity(middle) or identity(middle) != identity(after):
        raise RuntimeError("unstable_file")
    return first

def object_value(raw):
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("invalid_json")
    return value

def capture_index():
    base = os.path.join(ROOT, "observations", "trending", "v1", "captures")
    result = {}
    for current, directories, filenames in os.walk(base, topdown=True, followlinks=False):
        safe_directories = []
        for name in directories:
            info = os.lstat(os.path.join(current, name))
            if stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode):
                safe_directories.append(name)
        directories[:] = safe_directories
        for name in filenames:
            match = CAPTURE.fullmatch(name)
            if match is None:
                continue
            path = os.path.join(current, name)
            info = os.lstat(path)
            if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
                raise RuntimeError("unsafe_capture")
            slot = datetime.datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=datetime.timezone.utc)
            relative = os.path.relpath(path, ROOT).replace(os.sep, "/")
            if slot in result:
                raise RuntimeError("duplicate_capture")
            result[slot] = relative
    return result

def parse_capture(slot, relative):
    raw = read_stable(relative)
    value = object_value(raw)
    scheduled = datetime.datetime.fromisoformat(str(value.get("scheduledAt", "")).replace("Z", "+00:00"))
    expected = "trending-v1-" + slot.strftime("%Y%m%dT%H%M%SZ")
    if scheduled != slot or value.get("captureId") != expected or value.get("cadenceMinutes") != 120:
        raise RuntimeError("capture_identity")
    return value, raw

def latest_eligible(index):
    for slot in sorted(index, reverse=True):
        value, raw = parse_capture(slot, index[slot])
        if value.get("windowEligible") is True:
            return slot, value, raw
    raise RuntimeError("eligible_capture_missing")

index = capture_index()
latest_slot, latest_value, latest_raw = latest_eligible(index)
selected = []
cursor = latest_slot
for _ in range(37):
    relative = index.get(cursor)
    if relative is not None:
        value, raw = parse_capture(cursor, relative)
        if value.get("windowEligible") is True:
            selected.append((cursor, value, raw))
    cursor -= datetime.timedelta(hours=2)
selected.reverse()
if len(selected) < 2 or (selected[-1][0] - selected[0][0]).total_seconds() < 26 * 3600:
    raise RuntimeError("continuous_window_short")

pointer_raw = read_stable("current.json", 65536)
pointer = object_value(pointer_raw)
generation = pointer.get("generationId")
if not isinstance(generation, str) or GENERATION.fullmatch(generation) is None:
    raise RuntimeError("today_generation")
base = "generations/" + generation
manifest_raw = read_stable(base + "/manifest.json", 4 * 1024 * 1024)
manifest = object_value(manifest_raw)
if pointer.get("manifestSha256") != hashlib.sha256(manifest_raw).hexdigest() or manifest.get("generationId") != generation or manifest.get("state") != "ready":
    raise RuntimeError("today_manifest")
explosion_raw = read_stable(base + "/trending/explosion.json")
explosion = object_value(explosion_raw)
hashes = manifest.get("hashes")
if not isinstance(hashes, dict) or hashes.get("trending/explosion.json") != hashlib.sha256(explosion_raw).hexdigest():
    raise RuntimeError("today_explosion")
source_captures = explosion.get("sourceCaptures")
if not isinstance(source_captures, dict):
    raise RuntimeError("today_sources")
references = [source_captures.get("current")]
if source_captures.get("baseline") is not None:
    references.append(source_captures["baseline"])
references.extend(source_captures.get("partial") or [])
if source_captures.get("coverageWitness") is not None:
    references.append(source_captures["coverageWitness"])
generation_files = {}
for reference in references:
    if not isinstance(reference, dict):
        raise RuntimeError("today_source_reference")
    relative = reference.get("generationRelativePath")
    expected = reference.get("fileSha256")
    if not isinstance(relative, str) or not isinstance(expected, str) or hashes.get(relative) != expected:
        raise RuntimeError("today_source_reference")
    raw = read_stable(base + "/" + relative)
    if hashlib.sha256(raw).hexdigest() != expected:
        raise RuntimeError("today_source_hash")
    generation_files[relative] = raw

second_index = capture_index()
second_slot, second_value, second_latest_raw = latest_eligible(second_index)
if second_slot != latest_slot or second_value.get("captureId") != latest_value.get("captureId") or second_latest_raw != latest_raw:
    raise RuntimeError("observation_changed")
if read_stable("current.json", 65536) != pointer_raw or read_stable(base + "/manifest.json", 4 * 1024 * 1024) != manifest_raw or read_stable(base + "/trending/explosion.json") != explosion_raw:
    raise RuntimeError("today_changed")

encode = lambda raw: base64.b64encode(raw).decode("ascii")
payload = {
    "schemaVersion": 1,
    "captures": [{"captureId": value["captureId"], "content": encode(raw)} for _slot, value, raw in selected],
    "today": {
        "current": encode(pointer_raw),
        "manifest": encode(manifest_raw),
        "explosion": encode(explosion_raw),
        "generationFiles": {key: encode(value) for key, value in generation_files.items()},
    },
}
sys.stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))
"""


def _program(root: str) -> str:
    return _REMOTE_PROGRAM.replace("__REMOTE_ROOT__", repr(root))


def ssh_selection_source_runner(host: str, remote_root: str) -> bytes:
    if _HOST.fullmatch(host) is None or not remote_root.startswith("/") or "\x00" in remote_root:
        raise SelectionSourceError("rardar_selection_source_invalid_configuration", "Selection source sync is invalid")
    try:
        completed = subprocess.run(
            ["ssh", "-C", host, "sudo", "-n", "python3", "-"],
            input=_program(remote_root).encode("utf-8"),
            capture_output=True,
            check=False,
            timeout=600,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SelectionSourceError(
            "rardar_selection_source_remote_unavailable", "Selection source sync failed"
        ) from exc
    if completed.returncode != 0:
        raise SelectionSourceError("rardar_selection_source_remote_rejected", "Selection source sync was rejected")
    if not completed.stdout or len(completed.stdout) > _MAX_BUNDLE:
        raise SelectionSourceError("rardar_selection_source_bundle_invalid", "Selection source bundle is invalid")
    return completed.stdout


def local_selection_source_runner(source: Path) -> bytes:
    source = source.resolve()
    try:
        completed = subprocess.run(
            [sys.executable, "-c", _program(str(source))],
            capture_output=True,
            check=False,
            timeout=240,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SelectionSourceError(
            "rardar_selection_source_local_unavailable", "Local Selection source failed"
        ) from exc
    if completed.returncode != 0:
        raise SelectionSourceError("rardar_selection_source_local_rejected", "Local Selection source was rejected")
    if not completed.stdout or len(completed.stdout) > _MAX_BUNDLE:
        raise SelectionSourceError("rardar_selection_source_bundle_invalid", "Selection source bundle is invalid")
    return completed.stdout


def sync_selection_source(
    target: Path,
    *,
    host: str = "rardar-prod",
    remote_root: str = "/var/lib/rardar/data",
    source_dir: Path | None = None,
) -> SelectionSourceInstallResult:
    bundle = (
        local_selection_source_runner(source_dir)
        if source_dir is not None
        else ssh_selection_source_runner(host, remote_root)
    )
    return install_selection_source(target.resolve(), build_selection_source(bundle))


__all__ = [
    "BuiltSelectionSource",
    "LoadedSelectionSource",
    "SelectionSourceAdapter",
    "SelectionSourceError",
    "SelectionSourceInstallResult",
    "build_selection_source",
    "install_selection_source",
    "local_selection_source_runner",
    "ssh_selection_source_runner",
    "sync_selection_source",
]
