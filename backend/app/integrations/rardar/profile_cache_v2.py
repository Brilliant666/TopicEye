"""Evidence-content profile cache and retry ledger for Rardar Selection.

The cache deliberately separates reusable semantic profile content from the
Observation/Selection generation that currently projects that content. All
files live below the operator supplied cache root; this module never touches
the business database or a published Selection pointer.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError, model_validator
from pydantic_core import to_jsonable_python

from app.integrations.rardar.schemas import ExactExplosionProject
from app.integrations.rardar.serving_schemas import OfficialProjectProfile, ProjectEvidenceProjection

PROFILE_CACHE_IDENTITY_VERSION = 2
PROFILE_STORE_SCHEMA_VERSION = 2
PROFILE_ATTEMPT_SCHEMA_VERSION = 1
PROFILE_SANITIZER_VERSION = "rardar-profile-sanitizer-v1"
PROFILE_EXTRACTOR_VERSION = "rardar-profile-extractor-v1"
PROFILE_TRANSLATION_VERSION = "rardar-profile-translation-v1"

ProfileFailureCode = Literal[
    "profile_source_timeout",
    "profile_source_rate_limited",
    "profile_source_http_5xx",
    "profile_source_remote_disconnected",
    "profile_source_http_404",
    "profile_source_invalid",
    "profile_evidence_incomplete",
    "profile_evidence_mismatch",
    "profile_schema_invalid",
    "profile_translation_unavailable",
    "profile_model_unavailable",
    "profile_model_invalid_output",
    "profile_build_interrupted",
    "profile_path_unsafe",
    "profile_unknown_failure",
]

_REPARSE_POINT = 0x400
_HEX = r"^[a-f0-9]{64}$"
_SAFE_COMPONENT = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,190}$"
_DYNAMIC_PROFILE_KEYS = {
    "generationId",
    "repository",
    "htmlUrl",
    "evidenceDigest",
    "generatedAt",
    "readmePath",
    "readmeBlobSha",
    "selectedSections",
    "originalExcerpts",
    "startHere",
}
_RETRY_DELAYS = (timedelta(minutes=5), timedelta(minutes=30), timedelta(hours=2), timedelta(hours=6))


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ProfileCacheIntegrityError(ValueError):
    """A V2 cache, evidence binding, attempt, or path failed its integrity contract."""


def canonical_bytes(value: object) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    value = to_jsonable_python(value)
    return (
        json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def digest(value: object) -> str:
    raw = value if isinstance(value, bytes) else canonical_bytes(value)
    return hashlib.sha256(raw).hexdigest()


class ProfileCacheIdentityV2(_StrictModel):
    schemaVersion: Literal[2]
    repositoryId: int = Field(gt=0)
    profileEvidenceManifestDigest: str = Field(pattern=_HEX)
    descriptionDigest: str = Field(pattern=_HEX)
    readmePath: str | None = Field(default=None, max_length=500)
    readmeBlobSha: str | None = Field(default=None, pattern=r"^[A-Fa-f0-9]{7,64}$")
    readmeContentDigest: str = Field(pattern=_HEX)
    treeDigest: str = Field(pattern=_HEX)
    releaseEvidenceDigest: str | None = Field(default=None, pattern=_HEX)
    repositoryMetadataDigest: str = Field(pattern=_HEX)
    derivationMode: Literal["official_zh", "official_translated", "rardar_derived", "insufficient"]
    sanitizerVersion: str = Field(min_length=1, max_length=100)
    extractorVersion: str = Field(min_length=1, max_length=100)
    translationVersion: str = Field(min_length=1, max_length=100)
    profilePromptVersion: str = Field(min_length=1, max_length=100)
    profileSchemaVersion: str = Field(min_length=1, max_length=100)
    officialNarrativePromptVersion: str = Field(min_length=1, max_length=100)
    officialPositioningPromptVersion: str = Field(min_length=1, max_length=100)
    rardarAssessmentPromptVersion: str = Field(min_length=1, max_length=100)
    modelRouteIdentity: str | None = Field(default=None, pattern=_HEX)
    identityDigest: str = Field(pattern=_HEX)

    @model_validator(mode="after")
    def validate_digest(self) -> ProfileCacheIdentityV2:
        payload = self.model_dump(mode="json", exclude={"identityDigest"})
        if digest(payload) != self.identityDigest:
            raise ValueError("profile cache identity digest mismatch")
        return self


class ProfileProjectionBindingV1(_StrictModel):
    schemaVersion: Literal[1]
    repositoryId: int = Field(gt=0)
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    htmlUrl: str = Field(pattern=r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    defaultBranch: str = Field(min_length=1, max_length=250)
    selectionProvenance: str = Field(min_length=1, max_length=190)
    evidenceInventoryRevision: str = Field(pattern=_HEX)
    evidenceAliasDigest: str = Field(pattern=_HEX)
    bindingDigest: str = Field(pattern=_HEX)

    @model_validator(mode="after")
    def validate_digest(self) -> ProfileProjectionBindingV1:
        payload = self.model_dump(mode="json", exclude={"bindingDigest"})
        if digest(payload) != self.bindingDigest:
            raise ValueError("profile projection binding digest mismatch")
        return self


class ProfileStoreEnvelopeV2(_StrictModel):
    schemaVersion: Literal[2]
    cacheIdentity: ProfileCacheIdentityV2
    profileRevision: str = Field(pattern=_HEX)
    storedAt: AwareDatetime
    profile: OfficialProjectProfile
    evidence: ProjectEvidenceProjection
    deterministicFallbackUsed: bool
    migratedFrom: str | None = Field(default=None, max_length=500)
    reboundFromGeneration: str | None = Field(default=None, max_length=190)
    recordDigest: str = Field(pattern=_HEX)

    @model_validator(mode="after")
    def validate_record(self) -> ProfileStoreEnvelopeV2:
        payload = self.model_dump(mode="json", exclude={"recordDigest"})
        if digest(payload) != self.recordDigest:
            raise ValueError("profile store record digest mismatch")
        if self.profile.githubRepositoryId != self.cacheIdentity.repositoryId:
            raise ValueError("profile store repository identity mismatch")
        if self.profile.evidenceDigest != self.evidence.digest:
            raise ValueError("profile store evidence digest mismatch")
        if semantic_profile_revision(self.profile) != self.profileRevision:
            raise ValueError("profile store revision mismatch")
        return self


class ProfileAttemptRecordV1(_StrictModel):
    schemaVersion: Literal[1]
    attemptId: str = Field(pattern=_SAFE_COMPONENT)
    repositoryId: int = Field(gt=0)
    errorCode: ProfileFailureCode
    retryable: bool
    attemptCount: int = Field(ge=1, le=100000)
    firstAttemptAt: AwareDatetime
    lastAttemptAt: AwareDatetime
    nextRetryAt: AwareDatetime | None
    profileEvidenceDigest: str = Field(pattern=_HEX)
    sourceFailureStage: str = Field(min_length=1, max_length=100)
    safePublicCode: ProfileFailureCode
    recordDigest: str = Field(pattern=_HEX)

    @model_validator(mode="after")
    def validate_attempt(self) -> ProfileAttemptRecordV1:
        payload = self.model_dump(mode="json", exclude={"recordDigest"})
        if digest(payload) != self.recordDigest:
            raise ValueError("profile attempt digest mismatch")
        if self.safePublicCode != self.errorCode:
            raise ValueError("profile attempt public code mismatch")
        if self.retryable != (self.nextRetryAt is not None):
            raise ValueError("profile attempt retry state mismatch")
        if self.lastAttemptAt < self.firstAttemptAt:
            raise ValueError("profile attempt timestamps are invalid")
        return self


def _without_projection(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if key in _DYNAMIC_PROFILE_KEYS or key == "claimEvidenceRefs" or key.endswith("EvidenceRefs"):
                continue
            result[key] = _without_projection(item)
        return result
    if isinstance(value, list):
        return [_without_projection(item) for item in value]
    return value


def semantic_profile_revision(profile: OfficialProjectProfile) -> str:
    return digest(_without_projection(profile.model_dump(mode="json")))


def _readme_content(evidence: ProjectEvidenceProjection) -> dict[str, Any]:
    return {
        "selectedSections": [item.model_dump(mode="json") for item in evidence.selectedSections],
        "originalExcerpts": evidence.originalExcerpts,
        "evidenceIndex": {key: value for key, value in evidence.evidenceIndex.items() if key.startswith("readme:")},
        "pathRefs": {key: value for key, value in evidence.pathRefs.items() if key.startswith("readme:")},
    }


def _tree_content(evidence: ProjectEvidenceProjection) -> dict[str, Any]:
    return {
        "topLevelTree": sorted(
            (
                item.model_dump(mode="json") if isinstance(item, BaseModel) else dict(item)
                for item in evidence.topLevelTree
            ),
            key=lambda item: (str(item.get("path", "")).casefold(), str(item.get("type", ""))),
        ),
        "evidenceIndex": {
            key: value
            for key, value in evidence.evidenceIndex.items()
            if key.startswith("path:") or key.startswith("documented-path:")
        },
        "pathRefs": {
            key: value
            for key, value in evidence.pathRefs.items()
            if key.startswith("path:") or key.startswith("documented-path:")
        },
    }


def profile_cache_identity(
    project: ExactExplosionProject,
    evidence: ProjectEvidenceProjection,
    *,
    derivation_mode: Literal["official_zh", "official_translated", "rardar_derived", "insufficient"],
    model_route_identity: str | None,
    profile_schema_version: str,
    profile_prompt_version: str,
    official_narrative_prompt_version: str,
    official_positioning_prompt_version: str,
    rardar_assessment_prompt_version: str,
) -> ProfileCacheIdentityV2:
    effective_model_route = (
        model_route_identity if derivation_mode in {"official_translated", "rardar_derived"} else None
    )
    description_digest = digest(evidence.evidenceIndex.get("description"))
    readme_content_digest = digest(_readme_content(evidence))
    tree_digest = digest(_tree_content(evidence))
    metadata_digest = digest(
        {
            "primaryLanguage": project.primaryLanguage,
            "topics": sorted(set(project.topics), key=str.casefold),
            "licenseSpdxId": project.licenseSpdxId,
            "sourceLanguage": evidence.sourceLanguage,
        }
    )
    manifest = {
        "repositoryId": project.githubRepositoryId,
        "descriptionDigest": description_digest,
        "readmePath": evidence.readmePath,
        "readmeBlobSha": evidence.readmeBlobSha,
        "readmeContentDigest": readme_content_digest,
        "treeDigest": tree_digest,
        "releaseEvidenceDigest": None,
        "repositoryMetadataDigest": metadata_digest,
    }
    payload = {
        "schemaVersion": PROFILE_CACHE_IDENTITY_VERSION,
        "repositoryId": project.githubRepositoryId,
        "profileEvidenceManifestDigest": digest(manifest),
        **{key: value for key, value in manifest.items() if key != "repositoryId"},
        "derivationMode": derivation_mode,
        "sanitizerVersion": PROFILE_SANITIZER_VERSION,
        "extractorVersion": PROFILE_EXTRACTOR_VERSION,
        "translationVersion": PROFILE_TRANSLATION_VERSION,
        "profilePromptVersion": profile_prompt_version,
        "profileSchemaVersion": profile_schema_version,
        "officialNarrativePromptVersion": official_narrative_prompt_version,
        "officialPositioningPromptVersion": official_positioning_prompt_version,
        "rardarAssessmentPromptVersion": rardar_assessment_prompt_version,
        "modelRouteIdentity": effective_model_route,
    }
    payload["identityDigest"] = digest(payload)
    return ProfileCacheIdentityV2.model_validate(payload, strict=True)


def _evidence_source_identity(
    evidence: ProjectEvidenceProjection,
    identity: ProfileCacheIdentityV2,
    reference: str,
) -> tuple[str, int, str, str, str] | None:
    excerpt = evidence.evidenceIndex.get(reference)
    if not isinstance(excerpt, str):
        return None
    if reference == "repository":
        return (
            "repository",
            evidence.githubRepositoryId,
            "github.repository",
            str(evidence.githubRepositoryId),
            digest(excerpt),
        )
    if reference == "description":
        return (
            "description",
            evidence.githubRepositoryId,
            "github.description",
            identity.descriptionDigest,
            digest(excerpt),
        )
    if reference.startswith("readme:"):
        path = evidence.pathRefs.get(reference) or evidence.readmePath
        if not path or not evidence.readmeBlobSha:
            return None
        return ("readme", evidence.githubRepositoryId, path, evidence.readmeBlobSha, digest(excerpt))
    if reference.startswith("path:") or reference.startswith("documented-path:"):
        path = evidence.pathRefs.get(reference) or reference.split(":", 1)[1]
        return ("tree", evidence.githubRepositoryId, path, identity.treeDigest, digest(excerpt))
    return None


def evidence_ref_remap(
    old_evidence: ProjectEvidenceProjection,
    old_identity: ProfileCacheIdentityV2,
    current_evidence: ProjectEvidenceProjection,
    current_identity: ProfileCacheIdentityV2,
) -> dict[str, str]:
    if old_evidence.githubRepositoryId != current_evidence.githubRepositoryId:
        raise ProfileCacheIntegrityError("cross-repository profile evidence")
    current: dict[tuple[str, int, str, str, str], list[str]] = {}
    for reference in current_evidence.evidenceIndex:
        source = _evidence_source_identity(current_evidence, current_identity, reference)
        if source is not None:
            current.setdefault(source, []).append(reference)
    result: dict[str, str] = {}
    for reference in old_evidence.evidenceIndex:
        source = _evidence_source_identity(old_evidence, old_identity, reference)
        matches = current.get(source, []) if source is not None else []
        if len(matches) != 1:
            raise ProfileCacheIntegrityError(f"profile evidence reference cannot be mapped: {reference}")
        result[reference] = matches[0]
    return result


def _map_reference(reference: Any, mapping: dict[str, str]) -> str:
    if not isinstance(reference, str) or reference not in mapping:
        raise ProfileCacheIntegrityError("profile evidence reference is unavailable")
    return mapping[reference]


def _remap_references(value: Any, mapping: dict[str, str], *, key: str | None = None) -> Any:
    if isinstance(value, dict):
        if key == "claimEvidenceRefs":
            return {claim: [_map_reference(item, mapping) for item in refs] for claim, refs in value.items()}
        return {name: _remap_references(item, mapping, key=name) for name, item in value.items()}
    if isinstance(value, list):
        if key is not None and key.endswith("EvidenceRefs"):
            return [_map_reference(item, mapping) for item in value]
        return [_remap_references(item, mapping, key=key) for item in value]
    return value


def rebind_profile(
    envelope: ProfileStoreEnvelopeV2,
    current_identity: ProfileCacheIdentityV2,
    current_evidence: ProjectEvidenceProjection,
    project: ExactExplosionProject,
    generation_id: str,
    *,
    start_here: list[Any],
) -> tuple[OfficialProjectProfile, ProfileProjectionBindingV1, int]:
    if envelope.cacheIdentity != current_identity:
        raise ProfileCacheIntegrityError("profile evidence manifest differs")
    mapping = evidence_ref_remap(envelope.evidence, envelope.cacheIdentity, current_evidence, current_identity)
    payload = _remap_references(envelope.profile.model_dump(mode="python"), mapping)
    payload.update(
        {
            "githubRepositoryId": project.githubRepositoryId,
            "repository": project.repository,
            "htmlUrl": str(project.htmlUrl),
            "generationId": generation_id,
            "readmePath": current_evidence.readmePath,
            "readmeBlobSha": current_evidence.readmeBlobSha,
            "selectedSections": [item.model_dump(mode="json") for item in current_evidence.selectedSections],
            "originalExcerpts": current_evidence.originalExcerpts,
            "startHere": [item.model_dump(mode="json") if isinstance(item, BaseModel) else item for item in start_here],
            "evidenceDigest": current_evidence.digest,
        }
    )
    profile = OfficialProjectProfile.model_validate(payload, strict=True)
    aliases = {
        old: {"current": new, "source": _evidence_source_identity(current_evidence, current_identity, new)}
        for old, new in sorted(mapping.items())
    }
    binding_payload = {
        "schemaVersion": 1,
        "repositoryId": project.githubRepositoryId,
        "repository": project.repository,
        "htmlUrl": str(project.htmlUrl),
        "defaultBranch": project.defaultBranch,
        "selectionProvenance": generation_id,
        "evidenceInventoryRevision": current_evidence.digest,
        "evidenceAliasDigest": digest(aliases),
    }
    binding_payload["bindingDigest"] = digest(binding_payload)
    binding = ProfileProjectionBindingV1.model_validate(binding_payload, strict=True)
    return profile, binding, len(mapping)


def _is_reparse(info: os.stat_result) -> bool:
    return bool(getattr(info, "st_file_attributes", 0) & _REPARSE_POINT)


def _relative_parts(root: Path, path: Path) -> tuple[Path, tuple[str, ...]]:
    absolute_root = Path(os.path.abspath(root))
    absolute_path = Path(os.path.abspath(path))
    try:
        relative = absolute_path.relative_to(absolute_root)
    except ValueError:
        raise ProfileCacheIntegrityError("profile cache path escapes its root") from None
    if any(part in {"", ".", ".."} for part in relative.parts):
        raise ProfileCacheIntegrityError("profile cache path is unsafe")
    return absolute_root, relative.parts


def _ensure_plain_directory(path: Path, *, root: Path | None = None) -> None:
    boundary = path if root is None else root
    absolute_root, parts = _relative_parts(boundary, path)
    absolute_root.mkdir(parents=True, exist_ok=True)
    current = absolute_root
    for component in (None, *parts):
        if component is not None:
            current /= component
            current.mkdir(exist_ok=True)
        info = os.lstat(current)
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or _is_reparse(info):
            raise ProfileCacheIntegrityError("profile cache path is unsafe")


def _read_plain(
    path: Path,
    maximum: int = 4 * 1024 * 1024,
    *,
    root: Path | None = None,
) -> bytes | None:
    if root is not None:
        absolute_root, parts = _relative_parts(root, path)
        current = absolute_root
        for component in parts[:-1]:
            try:
                info = os.lstat(current)
            except FileNotFoundError:
                return None
            if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or _is_reparse(info):
                raise ProfileCacheIntegrityError("profile cache path is unsafe")
            current /= component
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            return None
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or _is_reparse(info):
            raise ProfileCacheIntegrityError("profile cache path is unsafe")
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return None
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or _is_reparse(info)
        or getattr(info, "st_nlink", 1) != 1
        or info.st_size > maximum
    ):
        raise ProfileCacheIntegrityError("profile cache file is unsafe")
    raw = path.read_bytes()
    if len(raw) != info.st_size:
        raise ProfileCacheIntegrityError("profile cache file changed while reading")
    return raw


def _atomic(path: Path, raw: bytes, *, root: Path) -> None:
    _ensure_plain_directory(path.parent, root=root)
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


def profile_store_path(cache_root: Path, identity: ProfileCacheIdentityV2) -> Path:
    return cache_root / "profile-store" / "v2" / str(identity.repositoryId) / f"{identity.identityDigest}.json"


def load_profile_store(cache_root: Path, identity: ProfileCacheIdentityV2) -> ProfileStoreEnvelopeV2 | None:
    raw = _read_plain(profile_store_path(cache_root, identity), root=cache_root)
    if raw is None:
        return None
    try:
        return ProfileStoreEnvelopeV2.model_validate_json(raw, strict=True)
    except (ValidationError, ValueError) as exc:
        raise ProfileCacheIntegrityError("profile cache record is invalid") from exc


def store_profile(
    cache_root: Path,
    identity: ProfileCacheIdentityV2,
    profile: OfficialProjectProfile,
    evidence: ProjectEvidenceProjection,
    *,
    deterministic_fallback_used: bool,
    migrated_from: str | None = None,
    rebound_from_generation: str | None = None,
) -> ProfileStoreEnvelopeV2:
    payload = {
        "schemaVersion": PROFILE_STORE_SCHEMA_VERSION,
        "cacheIdentity": identity,
        "profileRevision": semantic_profile_revision(profile),
        "storedAt": datetime.now(UTC),
        "profile": profile,
        "evidence": evidence,
        "deterministicFallbackUsed": deterministic_fallback_used,
        "migratedFrom": migrated_from,
        "reboundFromGeneration": rebound_from_generation,
    }
    payload["recordDigest"] = digest(payload)
    envelope = ProfileStoreEnvelopeV2.model_validate(payload, strict=True)
    path = profile_store_path(cache_root, identity)
    raw = canonical_bytes(envelope)
    existing = _read_plain(path, root=cache_root)
    if existing is not None:
        try:
            loaded = ProfileStoreEnvelopeV2.model_validate_json(existing, strict=True)
        except (ValidationError, ValueError) as exc:
            raise ProfileCacheIntegrityError("profile cache record is invalid") from exc
        if loaded.cacheIdentity != envelope.cacheIdentity or loaded.profileRevision != envelope.profileRevision:
            raise ProfileCacheIntegrityError("profile cache identity collision")
        return loaded
    _atomic(path, raw, root=cache_root)
    return envelope


def _attempt_directory(cache_root: Path, repository_id: int, evidence_digest: str) -> Path:
    return cache_root / "profile-attempts" / "v1" / str(repository_id) / evidence_digest


def list_attempts(cache_root: Path, repository_id: int, evidence_digest: str) -> list[ProfileAttemptRecordV1]:
    directory = _attempt_directory(cache_root, repository_id, evidence_digest)
    if not directory.exists():
        return []
    _ensure_plain_directory(directory, root=cache_root)
    result: list[ProfileAttemptRecordV1] = []
    for path in sorted(directory.glob("*.json"))[-128:]:
        raw = _read_plain(path, maximum=128 * 1024, root=cache_root)
        if raw is not None:
            try:
                result.append(ProfileAttemptRecordV1.model_validate_json(raw, strict=True))
            except (ValidationError, ValueError) as exc:
                raise ProfileCacheIntegrityError("profile attempt record is invalid") from exc
    return sorted(result, key=lambda item: (item.lastAttemptAt, item.attemptId))


def latest_attempt(cache_root: Path, repository_id: int, evidence_digest: str) -> ProfileAttemptRecordV1 | None:
    attempts = list_attempts(cache_root, repository_id, evidence_digest)
    return attempts[-1] if attempts else None


def retry_is_due(
    cache_root: Path,
    repository_id: int,
    evidence_digest: str,
    *,
    now: datetime | None = None,
    force_retryable: bool = False,
) -> bool:
    last = latest_attempt(cache_root, repository_id, evidence_digest)
    if last is None:
        return True
    if force_retryable and last.retryable:
        return True
    if not last.retryable:
        return False
    return last.nextRetryAt is not None and (now or datetime.now(UTC)) >= last.nextRetryAt


def record_failure(
    cache_root: Path,
    repository_id: int,
    evidence_digest: str,
    *,
    error_code: ProfileFailureCode,
    retryable: bool,
    source_failure_stage: str,
    now: datetime | None = None,
) -> ProfileAttemptRecordV1:
    current = (now or datetime.now(UTC)).astimezone(UTC)
    attempts = list_attempts(cache_root, repository_id, evidence_digest)
    count = len(attempts) + 1
    first = attempts[0].firstAttemptAt if attempts else current
    delay = _RETRY_DELAYS[min(count - 1, len(_RETRY_DELAYS) - 1)] if retryable else None
    if error_code == "profile_source_http_404" and delay is not None:
        delay = max(delay, timedelta(hours=2))
    attempt_id = (
        f"{current.strftime('%Y%m%dT%H%M%S%fZ')}-"
        f"{digest({'repositoryId': repository_id, 'evidence': evidence_digest, 'count': count, 'error': error_code})[:12]}"
    )
    payload = {
        "schemaVersion": PROFILE_ATTEMPT_SCHEMA_VERSION,
        "attemptId": attempt_id,
        "repositoryId": repository_id,
        "errorCode": error_code,
        "retryable": retryable,
        "attemptCount": count,
        "firstAttemptAt": first,
        "lastAttemptAt": current,
        "nextRetryAt": current + delay if delay is not None else None,
        "profileEvidenceDigest": evidence_digest,
        "sourceFailureStage": source_failure_stage,
        "safePublicCode": error_code,
    }
    payload["recordDigest"] = digest(payload)
    record = ProfileAttemptRecordV1.model_validate(payload, strict=True)
    path = _attempt_directory(cache_root, repository_id, evidence_digest) / f"{attempt_id}.json"
    _atomic(path, canonical_bytes(record), root=cache_root)
    return record


def retryable_error(code: ProfileFailureCode) -> bool:
    return code in {
        "profile_source_timeout",
        "profile_source_rate_limited",
        "profile_source_http_5xx",
        "profile_source_remote_disconnected",
        "profile_source_http_404",
        "profile_translation_unavailable",
        "profile_model_unavailable",
        "profile_build_interrupted",
        "profile_unknown_failure",
    }


def _legacy_paths(cache_root: Path, repository_id: int) -> list[Path]:
    directory = cache_root / "profiles" / str(repository_id)
    if not directory.exists():
        return []
    _ensure_plain_directory(directory, root=cache_root)
    paths = sorted(directory.glob("*.json"))[:128]
    for path in paths:
        _read_plain(path, root=cache_root)
    return paths


def _load_legacy(
    path: Path,
    cache_root: Path,
) -> tuple[OfficialProjectProfile, ProjectEvidenceProjection, bool] | None:
    raw = _read_plain(path, root=cache_root)
    if raw is None:
        return None
    try:
        payload = json.loads(raw)
        if payload.get("schemaVersion") != 7 or not isinstance(payload.get("deterministicFallbackUsed"), bool):
            return None
        profile = OfficialProjectProfile.model_validate_json(
            json.dumps(payload.get("profile"), ensure_ascii=False, separators=(",", ":")),
            strict=True,
        )
        evidence = ProjectEvidenceProjection.model_validate_json(
            json.dumps(payload.get("evidence"), ensure_ascii=False, separators=(",", ":")),
            strict=True,
        )
    except (TypeError, ValueError):
        return None
    return profile, evidence, payload["deterministicFallbackUsed"]


def legacy_migration_candidate(
    cache_root: Path,
    project: ExactExplosionProject,
    current_evidence: ProjectEvidenceProjection,
    current_identities: list[ProfileCacheIdentityV2],
    *,
    versions: dict[str, str],
    publishable: Callable[[OfficialProjectProfile], bool],
) -> tuple[ProfileStoreEnvelopeV2, str] | None:
    expected = {item.identityDigest: item for item in current_identities}
    matches: list[
        tuple[
            Path,
            OfficialProjectProfile,
            ProjectEvidenceProjection,
            bool,
            ProfileCacheIdentityV2,
        ]
    ] = []
    for path in _legacy_paths(cache_root, project.githubRepositoryId):
        loaded = _load_legacy(path, cache_root)
        if loaded is None:
            continue
        profile, old_evidence, deterministic_fallback_used = loaded
        if (
            not publishable(profile)
            or profile.githubRepositoryId != project.githubRepositoryId
            or profile.profileSchemaVersion != versions["profileSchemaVersion"]
            or profile.promptVersion != versions["profilePromptVersion"]
            or profile.officialNarrativePromptVersion != versions["officialNarrativePromptVersion"]
            or profile.rardarAssessmentPromptVersion != versions["rardarAssessmentPromptVersion"]
        ):
            continue
        if profile.translationState == "translated" or (
            profile.officialNarrativeMode in {"official_translated", "rardar_derived"}
            and not deterministic_fallback_used
        ):
            # V1 did not persist model-route identity. Only direct official
            # extraction or explicitly deterministic content can prove that a
            # provider/model change would not alter the semantic payload.
            continue
        try:
            old_identity = profile_cache_identity(
                project,
                old_evidence,
                derivation_mode=profile.officialNarrativeMode or "insufficient",
                model_route_identity=None,
                profile_schema_version=versions["profileSchemaVersion"],
                profile_prompt_version=versions["profilePromptVersion"],
                official_narrative_prompt_version=versions["officialNarrativePromptVersion"],
                official_positioning_prompt_version=versions["officialPositioningPromptVersion"],
                rardar_assessment_prompt_version=versions["rardarAssessmentPromptVersion"],
            )
        except ValueError:
            continue
        current_identity = expected.get(old_identity.identityDigest)
        if current_identity is None:
            continue
        try:
            evidence_ref_remap(old_evidence, old_identity, current_evidence, current_identity)
        except ValueError:
            continue
        matches.append((path, profile, old_evidence, deterministic_fallback_used, current_identity))
    if not matches:
        return None
    # Finish the full compatibility preflight before the first V2 write. A
    # conflicting legacy history must remain available for operator review.
    revisions = {semantic_profile_revision(profile) for _path, profile, _evidence, _fallback, _identity in matches}
    if len(revisions) != 1:
        raise ProfileCacheIntegrityError("multiple legacy profiles conflict for one evidence identity")
    selected_path, profile, old_evidence, deterministic_fallback_used, current_identity = max(
        matches,
        key=lambda item: (item[1].generatedAt, item[0].as_posix()),
    )
    migrated_from = selected_path.relative_to(cache_root).as_posix()
    selected = store_profile(
        cache_root,
        current_identity,
        profile,
        old_evidence,
        deterministic_fallback_used=deterministic_fallback_used,
        migrated_from=migrated_from,
        rebound_from_generation=profile.generationId,
    )
    return selected, migrated_from


__all__ = [
    "PROFILE_CACHE_IDENTITY_VERSION",
    "ProfileAttemptRecordV1",
    "ProfileCacheIntegrityError",
    "ProfileCacheIdentityV2",
    "ProfileFailureCode",
    "ProfileProjectionBindingV1",
    "ProfileStoreEnvelopeV2",
    "canonical_bytes",
    "digest",
    "evidence_ref_remap",
    "latest_attempt",
    "legacy_migration_candidate",
    "load_profile_store",
    "profile_cache_identity",
    "profile_store_path",
    "rebind_profile",
    "record_failure",
    "retry_is_due",
    "retryable_error",
    "semantic_profile_revision",
    "store_profile",
]
