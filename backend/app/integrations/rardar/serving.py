"""Build, install, and quickly load immutable Rardar serving projections."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import threading
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from app.integrations.rardar.adapter import RardarArtifactError, _SafeRoot, _strict_json
from app.integrations.rardar.schemas import ExactExplosionProject, ExplosionBoardResponse
from app.integrations.rardar.serving_profiles import (
    CollectedProjectProfile,
    ProfileBuildResult,
)
from app.integrations.rardar.serving_schemas import (
    OfficialProjectProfile,
    ProjectEvidenceProjection,
    ServingFile,
    ServingManifest,
    ServingPointer,
    ServingProfileSummary,
    ServingProjectDetail,
    ServingProjectRecord,
    ServingTodaySnapshot,
    TodayProject,
)

_SERVING_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,190}$")
_SOURCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,126}$")
_MAX_MANIFEST_BYTES = 512 * 1024
_MAX_TODAY_BYTES = 2 * 1024 * 1024
_MAX_PROJECT_BYTES = 4 * 1024 * 1024


class ServingProjectionError(RardarArtifactError):
    """A stable fail-closed error for serving projection consumers."""


class ProfileProvider(Protocol):
    def __call__(
        self,
        projects: list[ExactExplosionProject],
        generation_id: str,
        cache_root: Path,
    ) -> ProfileBuildResult: ...


@dataclass(frozen=True)
class BuiltServingProjection:
    serving_generation_id: str
    source_generation_id: str
    manifest_sha256: str
    source_manifest_sha256: str
    source_explosion_sha256: str
    pointer_raw: bytes
    files: dict[str, bytes]
    profile_summary: ServingProfileSummary
    profile_result: ProfileBuildResult


@dataclass(frozen=True)
class ServingInstallResult:
    serving_generation_id: str
    source_generation_id: str
    manifest_sha256: str
    created: bool
    changed: bool


@dataclass
class _CachedBundle:
    pointer_sha256: str
    pointer: ServingPointer
    manifest: ServingManifest
    today: ServingTodaySnapshot
    project_details: dict[int, ServingProjectDetail]


_CACHE_LOCK = threading.RLock()
_CURRENT_CACHE: dict[str, _CachedBundle] = {}
_SOURCE_CACHE: dict[tuple[str, str], _CachedBundle] = {}


def clear_serving_cache() -> None:
    with _CACHE_LOCK:
        _CURRENT_CACHE.clear()
        _SOURCE_CACHE.clear()


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _model_bytes(model: Any) -> bytes:
    return _canonical_bytes(model.model_dump(mode="json"))


def _fallback_profiles(
    projects: list[ExactExplosionProject],
    generation_id: str,
    _cache_root: Path,
) -> ProfileBuildResult:
    values: dict[int, CollectedProjectProfile] = {}
    for project in projects:
        generated_at = project.pushedAt or datetime(1970, 1, 1, tzinfo=UTC)
        description = project.description
        if description and re.search(r"[\u3400-\u9fff]", description):
            summary = description
            source_label = "GitHub Description"
            source_language = "zh"
            translation_state = "not_needed"
        elif description:
            summary = f"官方原文：{description}"
            source_label = "GitHub Description"
            source_language = "en"
            translation_state = "pending"
        else:
            summary = "官方资料暂未提供可验证的项目简介。"
            source_label = "受限概括"
            source_language = None
            translation_state = "unavailable"
        evidence_payload = {
            "schemaVersion": 1,
            "githubRepositoryId": project.githubRepositoryId,
            "repository": project.repository,
            "generationId": generation_id,
            "readmePath": None,
            "readmeBlobSha": None,
            "sourceLanguage": source_language,
            "selectedSections": [],
            "originalExcerpts": [],
            "topLevelTree": [],
            "evidenceIndex": {
                "repository": "官方 GitHub 仓库身份",
                **({"description": description} if description else {}),
            },
            "pathRefs": {},
        }
        evidence_payload["digest"] = _sha(_canonical_bytes(evidence_payload))
        evidence = ProjectEvidenceProjection.model_validate(evidence_payload, strict=True)
        ref = "description" if description else "repository"
        profile = OfficialProjectProfile(
            profileSchemaVersion="rardar-project-profile-v3",
            promptVersion="rardar-project-profile-zh-v4",
            githubRepositoryId=project.githubRepositoryId,
            repository=project.repository,
            htmlUrl=project.htmlUrl,
            generationId=generation_id,
            profileState="partial" if description else "source_unavailable",
            officialSummaryZh=summary,
            sourceLabel=source_label,
            sourceLanguage=source_language,
            capabilityBulletsZh=[],
            capabilities=[],
            productFormsZh=[],
            supportedEnvironmentsZh=[],
            primaryUseCasesZh=[],
            deliveryFormsZh=[],
            claimEvidenceRefs={summary: [ref]},
            readmePath=None,
            readmeBlobSha=None,
            selectedSections=[],
            originalExcerpts=[],
            startHere=[],
            evidenceDigest=evidence.digest,
            generatedAt=generated_at,
            translationState=translation_state,
        )
        values[project.githubRepositoryId] = CollectedProjectProfile(
            profile=profile,
            evidence=evidence,
            github_requests=0,
            readme_cache_hit=False,
            translation_calls=0,
            translation_cache_hit=False,
        )
    return ProfileBuildResult(
        profiles=values,
        github_requests=0,
        readme_cache_hits=0,
        translation_calls=0,
        translation_cache_hits=0,
    )


def _summary(profiles: dict[int, CollectedProjectProfile]) -> ServingProfileSummary:
    states = [value.profile.profileState for value in profiles.values()]
    chinese = sum(
        bool(re.search(r"[\u3400-\u9fff]", value.profile.officialSummaryZh.removeprefix("官方原文：")))
        for value in profiles.values()
    )
    return ServingProfileSummary(
        total=len(states),
        complete=states.count("complete"),
        partial=states.count("partial"),
        sourceUnavailable=states.count("source_unavailable"),
        chineseSummaries=chinese,
    )


def build_serving_projection(
    *,
    board: ExplosionBoardResponse,
    source_manifest_sha256: str,
    source_explosion_sha256: str,
    synced_at: datetime | None,
    source_host: str | None,
    cache_root: Path,
    profile_provider: ProfileProvider | None = None,
) -> BuiltServingProjection:
    """Build a fully validated projection in memory before any activation write."""

    generation_id = board.generationId
    if not generation_id or not _SOURCE_ID.fullmatch(generation_id):
        raise ServingProjectionError("rardar_serving_source_invalid", "Serving source generation is invalid")
    projects = list(board.exactRanked[:20])
    provider = profile_provider or _fallback_profiles
    profile_result = provider(projects, generation_id, cache_root)
    expected_ids = {project.githubRepositoryId for project in projects}
    if set(profile_result.profiles) != expected_ids:
        raise ServingProjectionError("rardar_serving_profile_inventory_invalid", "Profile inventory is incomplete")
    profile_summary = _summary(profile_result.profiles)
    projection_identity = _sha(
        _canonical_bytes(
            {
                "sourceGenerationId": generation_id,
                "sourceManifestSha256": source_manifest_sha256,
                "sourceExplosionSha256": source_explosion_sha256,
                "profiles": {
                    str(identifier): {
                        "profile": value.profile.model_dump(mode="json"),
                        "evidence": value.evidence.model_dump(mode="json"),
                    }
                    for identifier, value in sorted(profile_result.profiles.items())
                },
            }
        )
    )
    serving_generation_id = f"{generation_id}--{projection_identity[:16]}"
    generated_at = board.publishedAt
    today_projects: list[TodayProject] = []
    project_files: dict[str, bytes] = {}
    evidence_files: dict[str, bytes] = {}
    for project in projects:
        collected = profile_result.profiles[project.githubRepositoryId]
        profile = collected.profile
        today_project = TodayProject.model_validate(
            project.model_dump(mode="python")
            | {
                "profileState": profile.profileState,
                "officialSummaryZh": profile.officialSummaryZh,
                "sourceLabel": profile.sourceLabel,
                "sourceLanguage": profile.sourceLanguage,
                "capabilityBulletsZh": profile.capabilityBulletsZh[:4],
                "capabilities": profile.capabilities[:4],
                "translationState": profile.translationState,
            },
            strict=True,
        )
        today_projects.append(today_project)
        record = ServingProjectRecord(
            schemaVersion=3,
            generationId=generation_id,
            servingGenerationId=serving_generation_id,
            project=today_project,
            profile=profile,
            coverage=board.coverage,
            conflictCount=board.conflictCount,
        )
        project_files[f"projects/{project.githubRepositoryId}.json"] = _model_bytes(record)
        evidence_files[f"evidence/{project.githubRepositoryId}.json"] = _model_bytes(collected.evidence)

    today = ServingTodaySnapshot(
        schemaVersion=3,
        state=board.state,
        reason=board.reason,
        generationId=generation_id,
        publishedAt=board.publishedAt,
        capturedAt=board.capturedAt,
        window=board.window,
        coverage=board.coverage,
        exactRanked=today_projects,
        pendingRanked=board.pendingRanked[:20],
        conflictCount=board.conflictCount,
        sourceStatus=board.sourceStatus,
        dataMode=board.dataMode,
        dataLabel=board.dataLabel if board.dataMode == "demo" else "Rardar 已验证 Serving 快照",
        syncedAt=synced_at,
        sourceHost=source_host,
        manifestSha256=source_manifest_sha256,
        artifactSha256=source_explosion_sha256,
        servingGenerationId=serving_generation_id,
        profileSummary=profile_summary,
    )
    today_raw = _model_bytes(today)
    files = {"today.json": today_raw, **project_files, **evidence_files}
    project_inventory = {
        str(identifier): ServingFile(
            path=f"projects/{identifier}.json",
            sha256=_sha(project_files[f"projects/{identifier}.json"]),
            bytes=len(project_files[f"projects/{identifier}.json"]),
        )
        for identifier in sorted(expected_ids)
    }
    evidence_inventory = {
        str(identifier): ServingFile(
            path=f"evidence/{identifier}.json",
            sha256=_sha(evidence_files[f"evidence/{identifier}.json"]),
            bytes=len(evidence_files[f"evidence/{identifier}.json"]),
        )
        for identifier in sorted(expected_ids)
    }
    manifest = ServingManifest(
        schemaVersion=3,
        state="ready",
        servingGenerationId=serving_generation_id,
        sourceGenerationId=generation_id,
        sourceManifestSha256=source_manifest_sha256,
        sourceExplosionSha256=source_explosion_sha256,
        today=ServingFile(path="today.json", sha256=_sha(today_raw), bytes=len(today_raw)),
        projects=project_inventory,
        evidence=evidence_inventory,
        generatedAt=generated_at,
        profileSummary=profile_summary,
    )
    manifest_raw = _model_bytes(manifest)
    files["manifest.json"] = manifest_raw
    pointer = ServingPointer(
        schemaVersion=3,
        servingGenerationId=serving_generation_id,
        sourceGenerationId=generation_id,
        manifestSha256=_sha(manifest_raw),
        activatedAt=generated_at,
    )
    pointer_raw = _model_bytes(pointer)
    _validate_built_projection(pointer_raw, files)
    return BuiltServingProjection(
        serving_generation_id=serving_generation_id,
        source_generation_id=generation_id,
        manifest_sha256=_sha(manifest_raw),
        source_manifest_sha256=source_manifest_sha256,
        source_explosion_sha256=source_explosion_sha256,
        pointer_raw=pointer_raw,
        files=files,
        profile_summary=profile_summary,
        profile_result=profile_result,
    )


def _strict_model(raw: bytes, model: type[Any], code: str) -> Any:
    try:
        _strict_json(raw)
        return model.model_validate_json(raw, strict=True)
    except Exception as exc:
        raise ServingProjectionError(code, "Rardar serving data failed strict validation") from exc


def _validate_project_binding(
    record: ServingProjectRecord,
    evidence: ProjectEvidenceProjection,
    *,
    identifier: str,
    pointer: ServingPointer,
    today_project: TodayProject,
) -> None:
    evidence_payload = evidence.model_dump(mode="json", exclude={"digest"})
    if _sha(_canonical_bytes(evidence_payload)) != evidence.digest:
        raise ServingProjectionError("rardar_serving_evidence_digest_invalid", "Serving evidence digest is invalid")
    allowed_refs = set(evidence.evidenceIndex)
    claims = {
        record.profile.officialSummaryZh,
        *record.profile.capabilityBulletsZh,
        *record.profile.productFormsZh,
        *record.profile.supportedEnvironmentsZh,
        *record.profile.primaryUseCasesZh,
        *record.profile.deliveryFormsZh,
    }
    capability_refs = {reference for capability in record.profile.capabilities for reference in capability.evidenceRefs}
    if any(not record.profile.claimEvidenceRefs.get(claim) for claim in claims):
        raise ServingProjectionError("rardar_serving_evidence_ref_invalid", "Serving profile claim is missing evidence")
    claim_refs = {reference for references in record.profile.claimEvidenceRefs.values() for reference in references}
    section_refs = {reference for section in record.profile.selectedSections for reference in section.evidenceRefs}
    link_refs = {reference for link in record.profile.startHere for reference in link.evidenceRefs}
    if (
        not claim_refs.issubset(allowed_refs)
        or not capability_refs.issubset(allowed_refs)
        or not section_refs.issubset(allowed_refs)
        or not link_refs.issubset(allowed_refs)
    ):
        raise ServingProjectionError(
            "rardar_serving_evidence_ref_invalid", "Serving profile evidence references are invalid"
        )
    if (
        record.servingGenerationId != pointer.servingGenerationId
        or record.generationId != pointer.sourceGenerationId
        or record.project != today_project
        or str(record.project.githubRepositoryId) != identifier
        or evidence.githubRepositoryId != record.project.githubRepositoryId
        or evidence.repository != record.project.repository
        or evidence.generationId != record.generationId
        or evidence.digest != record.profile.evidenceDigest
        or evidence.readmePath != record.profile.readmePath
        or evidence.readmeBlobSha != record.profile.readmeBlobSha
        or evidence.selectedSections != record.profile.selectedSections
        or evidence.originalExcerpts != record.profile.originalExcerpts
    ):
        raise ServingProjectionError("rardar_serving_mixed_generation", "Serving project source binding is invalid")
    repository_url = str(record.profile.htmlUrl).rstrip("/") + "/"
    for link in record.profile.startHere:
        if not str(link.htmlUrl).startswith(repository_url):
            raise ServingProjectionError("rardar_serving_project_invalid", "Serving project link leaves its repository")
        if not any(evidence.pathRefs.get(reference) == link.path for reference in link.evidenceRefs):
            raise ServingProjectionError(
                "rardar_serving_evidence_ref_invalid", "Serving project path reference is invalid"
            )


def _validate_built_projection(pointer_raw: bytes, files: dict[str, bytes]) -> None:
    pointer = _strict_model(pointer_raw, ServingPointer, "rardar_serving_pointer_invalid")
    manifest_raw = files.get("manifest.json")
    if manifest_raw is None or _sha(manifest_raw) != pointer.manifestSha256:
        raise ServingProjectionError("rardar_serving_manifest_digest_invalid", "Serving manifest digest is invalid")
    manifest = _strict_model(manifest_raw, ServingManifest, "rardar_serving_manifest_invalid")
    if (
        manifest.servingGenerationId != pointer.servingGenerationId
        or manifest.sourceGenerationId != pointer.sourceGenerationId
    ):
        raise ServingProjectionError("rardar_serving_mixed_generation", "Serving pointer and manifest are mixed")
    inventory = [manifest.today, *manifest.projects.values(), *manifest.evidence.values()]
    if {item.path for item in inventory} != set(files) - {"manifest.json"}:
        raise ServingProjectionError("rardar_serving_inventory_invalid", "Serving file inventory is incomplete")
    for item in inventory:
        raw = files[item.path]
        if len(raw) != item.bytes or _sha(raw) != item.sha256:
            raise ServingProjectionError("rardar_serving_artifact_digest_invalid", "Serving artifact digest is invalid")
    today = _strict_model(files[manifest.today.path], ServingTodaySnapshot, "rardar_serving_today_invalid")
    if (
        today.generationId != pointer.sourceGenerationId
        or today.servingGenerationId != pointer.servingGenerationId
        or today.manifestSha256 != manifest.sourceManifestSha256
        or today.artifactSha256 != manifest.sourceExplosionSha256
        or today.profileSummary != manifest.profileSummary
    ):
        raise ServingProjectionError("rardar_serving_mixed_generation", "Serving Today source binding is invalid")
    today_projects = {str(project.githubRepositoryId): project for project in today.exactRanked}
    if len(today_projects) != len(today.exactRanked) or set(today_projects) != set(manifest.projects):
        raise ServingProjectionError("rardar_serving_inventory_invalid", "Serving Today project index is invalid")
    for identifier, project_file in manifest.projects.items():
        record = _strict_model(files[project_file.path], ServingProjectRecord, "rardar_serving_project_invalid")
        evidence = _strict_model(
            files[manifest.evidence[identifier].path],
            ProjectEvidenceProjection,
            "rardar_serving_evidence_invalid",
        )
        _validate_project_binding(
            record,
            evidence,
            identifier=identifier,
            pointer=pointer,
            today_project=today_projects[identifier],
        )


def _plain_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    info = os.lstat(path)
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise ServingProjectionError("rardar_serving_unsafe_path", "Serving path is not a plain directory")


def _atomic_bytes(path: Path, raw: bytes) -> None:
    _plain_directory(path.parent)
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


def _optional_plain_bytes(path: Path) -> bytes | None:
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise ServingProjectionError("rardar_serving_unsafe_path", "Serving pointer is not a plain file")
    return path.read_bytes()


def _existing_generation_matches(path: Path, files: dict[str, bytes]) -> bool:
    if not path.exists():
        return False
    safe = _SafeRoot(str(path))
    safe.ensure_available()
    expected = set(files)
    actual: set[str] = set()
    for directory, directories, filenames in os.walk(path, followlinks=False):
        directory_path = Path(directory)
        _plain_directory(directory_path)
        for name in directories:
            _plain_directory(directory_path / name)
        for name in filenames:
            relative = (directory_path / name).relative_to(path).as_posix()
            actual.add(relative)
            expected_raw = files.get(relative)
            if expected_raw is None:
                return False
            if safe.read_stable(relative, maximum_bytes=max(1, len(expected_raw))) != expected_raw:
                return False
    return actual == expected


def install_serving_projection(target: Path, built: BuiltServingProjection) -> ServingInstallResult:
    """Install one immutable generation and atomically activate its source/current pointers."""

    serving_root = target / "serving"
    generations = serving_root / "generations"
    sources = serving_root / "sources"
    _plain_directory(target)
    _plain_directory(serving_root)
    _plain_directory(generations)
    _plain_directory(sources)
    generation_path = generations / built.serving_generation_id
    created = False
    if generation_path.exists():
        if not _existing_generation_matches(generation_path, built.files):
            raise ServingProjectionError("rardar_serving_generation_conflict", "Immutable serving generation differs")
    else:
        stage = Path(tempfile.mkdtemp(prefix=".serving-staging-", dir=serving_root))
        try:
            for relative, raw in built.files.items():
                destination = stage.joinpath(*relative.split("/"))
                _plain_directory(destination.parent)
                destination.write_bytes(raw)
            _validate_built_projection(built.pointer_raw, built.files)
            os.replace(stage, generation_path)
            created = True
        except Exception:
            shutil.rmtree(stage, ignore_errors=True)
            raise

    source_pointer = sources / f"{built.source_generation_id}.json"
    current_pointer = serving_root / "current.json"
    old_source = _optional_plain_bytes(source_pointer)
    old_current = _optional_plain_bytes(current_pointer)
    active_matches = False
    if old_current:
        try:
            active = _strict_model(old_current, ServingPointer, "rardar_serving_pointer_invalid")
            active_matches = (
                active.servingGenerationId == built.serving_generation_id
                and active.sourceGenerationId == built.source_generation_id
                and active.manifestSha256 == built.manifest_sha256
            )
        except ServingProjectionError:
            active_matches = False
    if active_matches and old_source:
        try:
            source_active = _strict_model(old_source, ServingPointer, "rardar_serving_pointer_invalid")
            active_matches = source_active == _strict_model(
                old_current, ServingPointer, "rardar_serving_pointer_invalid"
            )
        except ServingProjectionError:
            active_matches = False
    if active_matches:
        return ServingInstallResult(
            serving_generation_id=built.serving_generation_id,
            source_generation_id=built.source_generation_id,
            manifest_sha256=built.manifest_sha256,
            created=created,
            changed=False,
        )
    changed = old_source != built.pointer_raw or old_current != built.pointer_raw
    source_changed = False
    current_changed = False
    try:
        _atomic_bytes(source_pointer, built.pointer_raw)
        source_changed = True
        _atomic_bytes(current_pointer, built.pointer_raw)
        current_changed = True
        loaded, _etag = ServingProjectionLoader(target).load_today_with_etag()
        if loaded.generationId != built.source_generation_id:
            raise ServingProjectionError("rardar_serving_activation_failed", "Serving pointer did not activate")
    except Exception:
        if current_changed:
            if old_current is None:
                current_pointer.unlink(missing_ok=True)
            else:
                _atomic_bytes(current_pointer, old_current)
        if source_changed:
            if old_source is None:
                source_pointer.unlink(missing_ok=True)
            else:
                _atomic_bytes(source_pointer, old_source)
        if created:
            shutil.rmtree(generation_path, ignore_errors=True)
        clear_serving_cache()
        raise
    clear_serving_cache()
    return ServingInstallResult(
        serving_generation_id=built.serving_generation_id,
        source_generation_id=built.source_generation_id,
        manifest_sha256=built.manifest_sha256,
        created=created,
        changed=changed,
    )


class ServingProjectionLoader:
    """Validate tiny serving files once and cache them until a pointer changes."""

    def __init__(self, root: Path | str):
        raw = str(root).strip()
        self.root_path = Path(raw) if raw else Path()
        self.cache_key = os.path.normcase(str(self.root_path.resolve(strict=False))) if raw else "<unconfigured>"
        self.safe = _SafeRoot(raw)

    def _pointer(self, relative: str) -> tuple[bytes, ServingPointer]:
        try:
            self.safe.ensure_available()
            raw = self.safe.read_stable(relative, maximum_bytes=64 * 1024)
        except (FileNotFoundError, OSError, ValueError, RardarArtifactError) as exc:
            raise ServingProjectionError("rardar_serving_unavailable", "Rardar serving pointer is unavailable") from exc
        pointer = _strict_model(raw, ServingPointer, "rardar_serving_pointer_invalid")
        return raw, pointer

    def _bundle(self, raw_pointer: bytes, pointer: ServingPointer) -> _CachedBundle:
        base = f"serving/generations/{pointer.servingGenerationId}"
        try:
            manifest_raw = self.safe.read_stable(f"{base}/manifest.json", maximum_bytes=_MAX_MANIFEST_BYTES)
        except (FileNotFoundError, OSError, ValueError, RardarArtifactError) as exc:
            raise ServingProjectionError(
                "rardar_serving_manifest_unavailable", "Serving manifest is unavailable"
            ) from exc
        if _sha(manifest_raw) != pointer.manifestSha256:
            raise ServingProjectionError("rardar_serving_manifest_digest_invalid", "Serving manifest digest is invalid")
        manifest = _strict_model(manifest_raw, ServingManifest, "rardar_serving_manifest_invalid")
        if (
            manifest.servingGenerationId != pointer.servingGenerationId
            or manifest.sourceGenerationId != pointer.sourceGenerationId
        ):
            raise ServingProjectionError("rardar_serving_mixed_generation", "Serving manifest source does not match")
        try:
            today_raw = self.safe.read_stable(f"{base}/{manifest.today.path}", maximum_bytes=_MAX_TODAY_BYTES)
        except (FileNotFoundError, OSError, ValueError, RardarArtifactError) as exc:
            raise ServingProjectionError(
                "rardar_serving_today_unavailable", "Serving Today snapshot is unavailable"
            ) from exc
        if len(today_raw) != manifest.today.bytes or _sha(today_raw) != manifest.today.sha256:
            raise ServingProjectionError("rardar_serving_artifact_digest_invalid", "Serving Today digest is invalid")
        today = _strict_model(today_raw, ServingTodaySnapshot, "rardar_serving_today_invalid")
        if (
            today.generationId != pointer.sourceGenerationId
            or today.servingGenerationId != pointer.servingGenerationId
            or today.manifestSha256 != manifest.sourceManifestSha256
            or today.artifactSha256 != manifest.sourceExplosionSha256
            or today.profileSummary != manifest.profileSummary
        ):
            raise ServingProjectionError("rardar_serving_mixed_generation", "Serving Today source binding is invalid")
        return _CachedBundle(_sha(raw_pointer), pointer, manifest, today, {})

    def _current_bundle(self) -> _CachedBundle:
        raw, pointer = self._pointer("serving/current.json")
        digest = _sha(raw)
        with _CACHE_LOCK:
            cached = _CURRENT_CACHE.get(self.cache_key)
            if cached and cached.pointer_sha256 == digest:
                return cached
            bundle = self._bundle(raw, pointer)
            _CURRENT_CACHE[self.cache_key] = bundle
            _SOURCE_CACHE[(self.cache_key, pointer.sourceGenerationId)] = bundle
            return bundle

    def _source_bundle(self, source_generation_id: str) -> _CachedBundle:
        if not _SOURCE_ID.fullmatch(source_generation_id):
            raise ServingProjectionError("rardar_serving_source_invalid", "Requested serving source is invalid")
        try:
            raw, pointer = self._pointer(f"serving/sources/{source_generation_id}.json")
        except ServingProjectionError as exc:
            if exc.code == "rardar_serving_unavailable":
                raise ServingProjectionError(
                    "rardar_serving_source_not_found",
                    "Requested serving source is not retained",
                ) from exc
            raise
        if pointer.sourceGenerationId != source_generation_id:
            raise ServingProjectionError("rardar_serving_mixed_generation", "Serving source pointer is mixed")
        digest = _sha(raw)
        key = (self.cache_key, source_generation_id)
        with _CACHE_LOCK:
            cached = _SOURCE_CACHE.get(key)
            if cached and cached.pointer_sha256 == digest:
                return cached
            bundle = self._bundle(raw, pointer)
            _SOURCE_CACHE[key] = bundle
            return bundle

    def load_today_with_etag(self) -> tuple[ServingTodaySnapshot, str]:
        bundle = self._current_bundle()
        return bundle.today, f'"{bundle.manifest.today.sha256}"'

    @staticmethod
    def _project_etag(bundle: _CachedBundle, identifier: str) -> str:
        identity = f"{bundle.manifest.projects[identifier].sha256}:{bundle.manifest.evidence[identifier].sha256}"
        return f'"{_sha(identity.encode("ascii"))}"'

    def load_project_with_etag(
        self,
        github_repository_id: int,
        source_generation_id: str,
    ) -> tuple[ServingProjectDetail, str]:
        if github_repository_id <= 0:
            raise ServingProjectionError("rardar_serving_project_invalid", "Requested project identity is invalid")
        bundle = self._source_bundle(source_generation_id)
        with _CACHE_LOCK:
            cached = bundle.project_details.get(github_repository_id)
            if cached:
                return cached, self._project_etag(bundle, str(github_repository_id))
            identifier = str(github_repository_id)
            project_file = bundle.manifest.projects.get(identifier)
            evidence_file = bundle.manifest.evidence.get(identifier)
            if project_file is None or evidence_file is None:
                raise ServingProjectionError("rardar_serving_project_not_found", "Project is absent from this snapshot")
            base = f"serving/generations/{bundle.pointer.servingGenerationId}"
            try:
                project_raw = self.safe.read_stable(f"{base}/{project_file.path}", maximum_bytes=_MAX_PROJECT_BYTES)
                evidence_raw = self.safe.read_stable(f"{base}/{evidence_file.path}", maximum_bytes=_MAX_PROJECT_BYTES)
            except (FileNotFoundError, OSError, ValueError, RardarArtifactError) as exc:
                raise ServingProjectionError(
                    "rardar_serving_project_unavailable", "Serving project is unavailable"
                ) from exc
            if (
                len(project_raw) != project_file.bytes
                or _sha(project_raw) != project_file.sha256
                or len(evidence_raw) != evidence_file.bytes
                or _sha(evidence_raw) != evidence_file.sha256
            ):
                raise ServingProjectionError(
                    "rardar_serving_artifact_digest_invalid", "Serving project digest is invalid"
                )
            record = _strict_model(project_raw, ServingProjectRecord, "rardar_serving_project_invalid")
            evidence = _strict_model(evidence_raw, ProjectEvidenceProjection, "rardar_serving_evidence_invalid")
            today_project = next(
                (project for project in bundle.today.exactRanked if project.githubRepositoryId == github_repository_id),
                None,
            )
            if today_project is None:
                raise ServingProjectionError(
                    "rardar_serving_inventory_invalid", "Serving project is absent from Today inventory"
                )
            _validate_project_binding(
                record,
                evidence,
                identifier=identifier,
                pointer=bundle.pointer,
                today_project=today_project,
            )
            detail = ServingProjectDetail(
                schemaVersion=record.schemaVersion,
                generationId=source_generation_id,
                servingGenerationId=bundle.pointer.servingGenerationId,
                project=record.project,
                profile=record.profile,
                evidence=evidence,
                coverage=record.coverage,
                conflictCount=record.conflictCount,
            )
            bundle.project_details[github_repository_id] = detail
            return detail, self._project_etag(bundle, identifier)


def source_hashes(root: Path, generation_id: str) -> tuple[str, str]:
    """Read only the already-audited source manifest/explosion digests for a rebuild."""

    if not _SOURCE_ID.fullmatch(generation_id):
        raise ServingProjectionError("rardar_serving_source_invalid", "Source generation is invalid")
    safe = _SafeRoot(str(root))
    try:
        manifest_raw = safe.read_stable(f"generations/{generation_id}/manifest.json", maximum_bytes=4 * 1024 * 1024)
        manifest = _strict_json(manifest_raw)
        explosion_digest = manifest.get("hashes", {}).get("trending/explosion.json")
    except (FileNotFoundError, OSError, ValueError, RardarArtifactError) as exc:
        raise ServingProjectionError("rardar_serving_source_invalid", "Source hashes are unavailable") from exc
    if not isinstance(explosion_digest, str) or not re.fullmatch(r"[a-f0-9]{64}", explosion_digest):
        raise ServingProjectionError("rardar_serving_source_invalid", "Source Explosion digest is invalid")
    return _sha(manifest_raw), explosion_digest
