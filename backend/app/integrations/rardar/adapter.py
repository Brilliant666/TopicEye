"""Fail-closed reader for one Rardar published generation per request."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from functools import cache
from pathlib import Path, PurePosixPath
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

from app.integrations.rardar.schemas import ExplosionBoardResponse

_GENERATION_ID = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,126}[A-Za-z0-9])?$")
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_GITHUB_URL = re.compile(r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_REPARSE_POINT = 0x400
_CONTRACT_ROOT = Path(__file__).with_name("contracts")


class RardarArtifactError(RuntimeError):
    """Stable public error classification without leaking host paths."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class _DuplicateKeyError(ValueError):
    pass


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")


def _strict_json(raw: bytes) -> dict[str, Any]:
    value = json.loads(
        raw.decode("utf-8", errors="strict"),
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_constant,
    )
    if not isinstance(value, dict):
        raise ValueError("JSON document must be an object")
    return value


def _capture_payload_digest(payload: dict[str, Any]) -> str:
    """Recompute the producer's digest over canonical JSON without ``digest``."""

    digestless = {key: value for key, value in payload.items() if key != "digest"}
    canonical = json.dumps(
        digestless,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _is_reparse(info: os.stat_result) -> bool:
    return bool(getattr(info, "st_file_attributes", 0) & _REPARSE_POINT)


def _identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        getattr(info, "st_file_attributes", 0),
    )


class _SafeRoot:
    """No-follow, bounded, stable reads beneath one normalized absolute root."""

    def __init__(self, configured: str) -> None:
        raw = configured.strip()
        if not raw:
            raise RardarArtifactError(
                "rardar_intelligence_not_configured",
                "Rardar intelligence data directory is not configured",
            )
        candidate = Path(raw)
        if not candidate.is_absolute() or os.path.normcase(raw) != os.path.normcase(os.path.normpath(raw)):
            raise RardarArtifactError(
                "rardar_intelligence_invalid_configuration",
                "Rardar intelligence data directory must be an absolute normalized path",
            )
        self.root = candidate

    def ensure_available(self) -> None:
        try:
            self._assert_component_chain(self.root, final_kind="directory")
        except FileNotFoundError as exc:
            raise RardarArtifactError(
                "rardar_intelligence_unavailable",
                "Rardar intelligence data directory is unavailable",
            ) from exc
        except (OSError, ValueError) as exc:
            raise RardarArtifactError(
                "rardar_intelligence_invalid_configuration",
                "Rardar intelligence data directory failed the path safety contract",
            ) from exc

    def _assert_component_chain(self, target: Path, *, final_kind: str) -> None:
        try:
            target.relative_to(self.root)
        except ValueError:
            if target != self.root:
                raise ValueError("path escapes configured root") from None

        # Inspect the configured root from its filesystem anchor, then every
        # descendant.  resolve() is intentionally not used because it follows
        # the exact links this boundary must reject.
        current = Path(target.anchor)
        parts = target.parts[1:] if target.anchor else target.parts
        for index, part in enumerate(parts):
            current = current / part
            info = os.lstat(current)
            if stat.S_ISLNK(info.st_mode) or _is_reparse(info):
                raise ValueError("symbolic link, junction, or reparse point rejected")
            is_final = index == len(parts) - 1
            if not is_final and not stat.S_ISDIR(info.st_mode):
                raise ValueError("non-directory path component rejected")
            if is_final and final_kind == "directory" and not stat.S_ISDIR(info.st_mode):
                raise ValueError("expected a directory")
            if is_final and final_kind == "file" and not stat.S_ISREG(info.st_mode):
                raise ValueError("expected a regular file")

    def path(self, relative: str) -> Path:
        if "\\" in relative:
            raise ValueError("backslash is not a generation path separator")
        parsed = PurePosixPath(relative)
        if parsed.is_absolute() or not parsed.parts or any(part in {"", ".", ".."} for part in parsed.parts):
            raise ValueError("unsafe generation-relative path")
        return self.root.joinpath(*parsed.parts)

    @staticmethod
    def _read_open_file(path: Path, maximum_bytes: int) -> tuple[bytes, tuple[int, int, int, int, int]]:
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or _is_reparse(info) or info.st_size > maximum_bytes:
                raise ValueError("file type or size rejected")
            chunks: list[bytes] = []
            remaining = maximum_bytes + 1
            while remaining:
                chunk = os.read(descriptor, min(1024 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
            if len(raw) > maximum_bytes:
                raise ValueError("file size rejected")
            after = os.fstat(descriptor)
            if _identity(info) != _identity(after):
                raise ValueError("file changed during read")
            return raw, _identity(after)
        finally:
            os.close(descriptor)

    def read_stable(self, relative: str, *, maximum_bytes: int) -> bytes:
        path = self.path(relative)
        self._assert_component_chain(path, final_kind="file")
        before = _identity(os.lstat(path))
        first, first_identity = self._read_open_file(path, maximum_bytes)
        self._assert_component_chain(path, final_kind="file")
        second, second_identity = self._read_open_file(path, maximum_bytes)
        after = _identity(os.lstat(path))
        if before != first_identity or first_identity != second_identity or second_identity != after or first != second:
            raise ValueError("file snapshot was not stable")
        return first


@cache
def _validator(contract_name: str) -> Draft202012Validator:
    schema = _strict_json((_CONTRACT_ROOT / contract_name).read_bytes())
    checker = FormatChecker()

    @checker.checks("repository")
    def repository_format(value: object) -> bool:
        return isinstance(value, str) and _REPOSITORY.fullmatch(value) is not None

    @checker.checks("http-url")
    def http_url_format(value: object) -> bool:
        return isinstance(value, str) and _GITHUB_URL.fullmatch(value) is not None

    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=checker)


def _validate(contract_name: str, value: dict[str, Any]) -> None:
    _validator(contract_name).validate(value)


class RardarIntelligenceAdapter:
    """Read an exact Rardar revision and project only verified facts into a DTO."""

    def __init__(self, root: _SafeRoot) -> None:
        self._root = root

    @classmethod
    def from_config(cls, configured: str) -> RardarIntelligenceAdapter:
        return cls(_SafeRoot(configured))

    def _json(self, relative: str, *, maximum_bytes: int, code: str, label: str) -> tuple[dict[str, Any], bytes]:
        try:
            raw = self._root.read_stable(relative, maximum_bytes=maximum_bytes)
            return _strict_json(raw), raw
        except RardarArtifactError:
            raise
        except (FileNotFoundError, OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            raise RardarArtifactError(code, f"Rardar {label} failed stable validation") from exc

    @staticmethod
    def _schema(contract: str, value: dict[str, Any], *, code: str, label: str) -> None:
        try:
            _validate(contract, value)
        except (ValidationError, ValueError) as exc:
            raise RardarArtifactError(code, f"Rardar {label} failed Schema validation") from exc

    def load_explosion_board(self) -> ExplosionBoardResponse:
        self._root.ensure_available()
        pointer, _ = self._json(
            "current.json",
            maximum_bytes=64 * 1024,
            code="rardar_current_pointer_invalid",
            label="current pointer",
        )
        self._schema(
            "current-generation.schema.json",
            pointer,
            code="rardar_current_pointer_invalid",
            label="current pointer",
        )
        generation_id = pointer["generationId"]
        if not _GENERATION_ID.fullmatch(generation_id):
            raise RardarArtifactError("rardar_current_pointer_invalid", "Rardar generation ID is unsafe")

        manifest_path = f"generations/{generation_id}/manifest.json"
        manifest, manifest_raw = self._json(
            manifest_path,
            maximum_bytes=4 * 1024 * 1024,
            code="rardar_generation_invalid",
            label="generation manifest",
        )
        if hashlib.sha256(manifest_raw).hexdigest() != pointer["manifestSha256"]:
            raise RardarArtifactError("rardar_generation_invalid", "Rardar manifest digest does not match the pointer")
        self._schema(
            "generation-manifest.schema.json",
            manifest,
            code="rardar_generation_invalid",
            label="generation manifest",
        )
        if manifest["generationId"] != generation_id or manifest["state"] != "ready":
            raise RardarArtifactError(
                "rardar_generation_invalid", "Rardar generation is not the selected ready generation"
            )
        artifacts = manifest["artifacts"]
        hashes = manifest["hashes"]
        if len(artifacts) != len(set(artifacts)) or set(artifacts) != set(hashes):
            raise RardarArtifactError("rardar_generation_invalid", "Rardar manifest artifact inventory is inconsistent")

        artifact_path = "trending/explosion.json"
        if artifact_path not in hashes:
            return ExplosionBoardResponse.model_validate_json(
                json.dumps(
                    {
                        "state": "not_ready",
                        "reason": "explosion_artifact_not_published",
                        "generationId": generation_id,
                        "publishedAt": pointer["publishedAt"],
                    }
                )
            )

        artifact, artifact_raw = self._json(
            f"generations/{generation_id}/{artifact_path}",
            maximum_bytes=16 * 1024 * 1024,
            code="rardar_generation_invalid",
            label="explosion artifact",
        )
        if hashlib.sha256(artifact_raw).hexdigest() != hashes[artifact_path]:
            raise RardarArtifactError("rardar_generation_invalid", "Rardar explosion artifact digest is invalid")
        self._schema(
            "trending-explosion-artifact.schema.json",
            artifact,
            code="rardar_generation_invalid",
            label="explosion artifact",
        )
        if artifact["generationId"] != generation_id:
            raise RardarArtifactError("rardar_generation_invalid", "Rardar artifact belongs to another generation")

        current = self._validate_semantics(generation_id, manifest, artifact)
        return self._to_response(pointer, artifact, current)

    def _source_bundle(
        self,
        generation_id: str,
        manifest: dict[str, Any],
        reference: dict[str, Any],
    ) -> dict[str, Any]:
        relative = reference["generationRelativePath"]
        if relative not in manifest["hashes"] or relative not in manifest["artifacts"]:
            raise RardarArtifactError("rardar_generation_invalid", "Rardar source copy is absent from the manifest")
        source, raw = self._json(
            f"generations/{generation_id}/{relative}",
            maximum_bytes=16 * 1024 * 1024,
            code="rardar_generation_invalid",
            label="source capture copy",
        )
        digest = hashlib.sha256(raw).hexdigest()
        if digest != manifest["hashes"][relative] or digest != reference["fileSha256"]:
            raise RardarArtifactError("rardar_generation_invalid", "Rardar source capture digest is invalid")
        self._schema(
            "trending-capture-bundle.schema.json",
            source,
            code="rardar_generation_invalid",
            label="source capture copy",
        )
        if _capture_payload_digest(source) != source["digest"]["value"]:
            raise RardarArtifactError("rardar_generation_invalid", "Rardar source capture payload digest is invalid")
        if (
            source["captureId"] != reference["captureId"]
            or source["scheduledAt"] != reference["scheduledAt"]
            or source["capturedAt"] != reference["capturedAt"]
            or source["coverageState"] != reference["coverageState"]
            or source["digest"]["value"] != reference["payloadDigestSha256"]
        ):
            raise RardarArtifactError("rardar_generation_invalid", "Rardar source capture provenance is inconsistent")
        return source

    def _validate_semantics(
        self,
        generation_id: str,
        manifest: dict[str, Any],
        artifact: dict[str, Any],
    ) -> dict[str, Any]:
        captures = artifact["sourceCaptures"]
        references = [captures["current"]]
        if captures["baseline"] is not None:
            references.append(captures["baseline"])
        references.extend(captures["partial"])
        if captures["coverageWitness"] is not None:
            references.append(captures["coverageWitness"])
        if len({item["generationRelativePath"] for item in references}) != len(references):
            raise RardarArtifactError("rardar_generation_invalid", "Rardar source capture paths are not unique")
        source_by_path = {
            reference["generationRelativePath"]: self._source_bundle(generation_id, manifest, reference)
            for reference in references
        }
        current = source_by_path[captures["current"]["generationRelativePath"]]
        baseline = (
            source_by_path[captures["baseline"]["generationRelativePath"]] if captures["baseline"] is not None else None
        )

        exact = artifact["exactRanked"]
        pending = artifact["pendingRanked"]
        conflicts = artifact["conflicts"]
        coverage = artifact["coverage"]
        if [item["rank"] for item in exact] != list(range(1, len(exact) + 1)):
            raise RardarArtifactError("rardar_generation_invalid", "Rardar exact ranks are not contiguous")
        if exact != sorted(
            exact,
            key=lambda item: (-item["observedStarDelta"], -item["totalStars"], item["repository"]),
        ):
            raise RardarArtifactError("rardar_generation_invalid", "Rardar exact ranking policy was not preserved")
        if [item["pendingRank"] for item in pending] != list(range(1, len(pending) + 1)):
            raise RardarArtifactError("rardar_generation_invalid", "Rardar pending ranks are not contiguous")
        expected_pending = sorted(
            pending,
            key=lambda item: (
                0 if item["observedWindowStarDelta"] is not None else 1,
                -(item["observedWindowStarDelta"] or 0),
                -item["totalStars"],
                item["repository"],
            ),
        )
        if pending != expected_pending:
            raise RardarArtifactError("rardar_generation_invalid", "Rardar pending ordering policy was not preserved")
        all_ids = [item["githubRepositoryId"] for group in (exact, pending, conflicts) for item in group]
        if len(all_ids) != len(set(all_ids)):
            raise RardarArtifactError("rardar_generation_invalid", "Rardar ranking partitions overlap")
        if (
            coverage["exactPublishedCount"] != len(exact)
            or coverage["pendingPublishedCount"] != len(pending)
            or coverage["conflictCount"] != len(conflicts)
        ):
            raise RardarArtifactError("rardar_generation_invalid", "Rardar coverage counts do not match the artifact")
        window = artifact["window"]
        for item in exact:
            if (
                item["windowStartedAt"] != window["startedAt"]
                or item["windowEndedAt"] != window["endedAt"]
                or item["currentCapturedAt"] != current["capturedAt"]
                or baseline is None
                or item["baselineCapturedAt"] != baseline["capturedAt"]
            ):
                raise RardarArtifactError("rardar_generation_invalid", "Rardar exact item provenance is inconsistent")
        if any(item["currentCapturedAt"] != current["capturedAt"] for item in pending):
            raise RardarArtifactError("rardar_generation_invalid", "Rardar pending item provenance is inconsistent")
        observation_by_id = {item["githubRepositoryId"]: item for item in current["observations"]}
        if len(observation_by_id) != len(current["observations"]):
            raise RardarArtifactError("rardar_generation_invalid", "Rardar current observations contain duplicate IDs")
        for item in (*exact, *pending):
            observation = observation_by_id.get(item["githubRepositoryId"])
            if observation is None or any(
                observation[key] != item[key]
                for key in ("repository", "htmlUrl", "totalStars", "primaryLanguage", "topics")
            ):
                raise RardarArtifactError(
                    "rardar_generation_invalid", "Rardar ranked facts do not match the current observation"
                )
        return current

    @staticmethod
    def _to_response(
        pointer: dict[str, Any], artifact: dict[str, Any], current: dict[str, Any]
    ) -> ExplosionBoardResponse:
        window_state = artifact["window"]["state"]
        state = "ready" if window_state == "exact" else window_state
        coverage = artifact["coverage"]
        captures = artifact["sourceCaptures"]
        observation_by_id = {item["githubRepositoryId"]: item for item in current["observations"]}

        def current_metadata(item: dict[str, Any]) -> dict[str, Any]:
            observation = observation_by_id[item["githubRepositoryId"]]
            return {
                "description": observation["description"],
                "forks": observation["forks"],
                "pushedAt": observation["pushedAt"],
                "defaultBranch": observation["defaultBranch"],
                "licenseSpdxId": observation["licenseSpdxId"],
            }

        payload = {
            "state": state,
            "generationId": pointer["generationId"],
            "publishedAt": pointer["publishedAt"],
            "capturedAt": captures["current"]["capturedAt"],
            "window": artifact["window"],
            "coverage": {
                "state": coverage["state"],
                "successfulQueryCount": coverage["currentSuccessfulQueryCount"],
                "failedQueryCount": coverage["currentFailedQueryCount"],
                "metadataFailureCount": coverage["currentMetadataFailureCount"],
                "exactCount": coverage["exactPublishedCount"],
                "pendingCount": coverage["pendingPublishedCount"],
                "conflictCount": coverage["conflictCount"],
            },
            "exactRanked": [
                (
                    {
                        key: item[key]
                        for key in (
                            "rank",
                            "githubRepositoryId",
                            "repository",
                            "htmlUrl",
                            "totalStars",
                            "baselineStars",
                            "observedStarDelta",
                            "windowStartedAt",
                            "windowEndedAt",
                            "primaryLanguage",
                            "topics",
                            "archived",
                            "fork",
                            "mirrorUrl",
                            "state",
                        )
                    }
                    | current_metadata(item)
                )
                for item in artifact["exactRanked"][:20]
            ],
            "pendingRanked": [
                (
                    {
                        key: item[key]
                        for key in (
                            "pendingRank",
                            "pendingReason",
                            "githubRepositoryId",
                            "repository",
                            "htmlUrl",
                            "totalStars",
                            "firstSeenAt",
                            "observedWindowHours",
                            "observedWindowStarDelta",
                            "observedWindowStartedAt",
                            "observedWindowEndedAt",
                            "primaryLanguage",
                            "topics",
                        )
                    }
                    | current_metadata(item)
                )
                for item in artifact["pendingRanked"][:20]
            ],
            "conflictCount": coverage["conflictCount"],
            "sourceStatus": {
                "currentCaptureId": captures["current"]["captureId"],
                "baselineCaptureId": captures["baseline"]["captureId"] if captures["baseline"] else None,
                "partialCaptureCount": len(captures["partial"]),
                "coverageWitnessCaptureId": (
                    captures["coverageWitness"]["captureId"] if captures["coverageWitness"] else None
                ),
            },
            "dataMode": "real",
            "dataLabel": "Rardar 生产快照",
        }
        return ExplosionBoardResponse.model_validate_json(json.dumps(payload))
