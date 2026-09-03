"""Immutable publication and static request-time loading for worth-seeing Selection."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError
from pydantic_core import to_jsonable_python

from app.integrations.rardar.adapter import RardarArtifactError, _SafeRoot
from app.integrations.rardar.selection import BuiltSelection
from app.integrations.rardar.selection_schemas import (
    SelectionArtifact,
    SelectionProjectContext,
    SelectionServingCard,
    SelectionServingFile,
    SelectionServingManifest,
    SelectionServingPointer,
    SelectionServingSnapshot,
)

_STORE = "discover-worth-seeing"
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,190}$")
_REPARSE_POINT = 0x400
_REASON_COPY = {
    "directly_reusable": "提供可以直接评估和接入的工程资产，适合先验证核心模块的复用边界。",
    "specific_problem_solution": "针对一个具体开发问题给出清晰实现，适合对照当前任务做最小验证。",
    "distinctive_implementation": "实现路径具有辨识度，值得阅读关键代码和架构取舍。",
    "reference_or_learning_value": "整理了可复核的实现或知识材料，适合作为设计与学习参考。",
}


class SelectionServingError(RardarArtifactError):
    pass


@dataclass(frozen=True)
class BuiltSelectionServing:
    selection_generation_id: str
    source_observation_set_id: str
    manifest_sha256: str
    pointer_raw: bytes
    files: dict[str, bytes]


@dataclass(frozen=True)
class SelectionInstallResult:
    selection_generation_id: str
    source_observation_set_id: str
    manifest_sha256: str
    created: bool
    changed: bool


def _canonical_bytes(value: object) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    value = to_jsonable_python(value)
    return (
        json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _strict(raw: bytes, model: type[Any], code: str) -> Any:
    try:
        return model.model_validate_json(raw, strict=True)
    except (ValidationError, ValueError) as exc:
        raise SelectionServingError(code, "Selection serving contract is invalid") from exc


def _fallback_identity(assessment: Any, profile: Any) -> str:
    value = (
        profile.identitySummaryZh
        or profile.officialSummaryZh
        or assessment.candidate.description
        or f"{assessment.candidate.repository} 的开源项目。"
    )
    cleaned = " ".join(str(value).split())
    if len(cleaned) < 4:
        cleaned = f"{assessment.candidate.repository} 开源项目"
    return cleaned[:180]


def _why_now(assessment: Any) -> str | None:
    if assessment.timeliness.verdict != "strong":
        return None
    reasons = set(assessment.timeliness.reasonCodes)
    if "genuinely_new_asset" in reasons:
        return "这是近期出现的新资产，当前适合尽早核验它的实现与采用边界。"
    if "meaningful_release" in reasons:
        return "近期发布包含可验证的实质变化，值得现在重新评估。"
    if "meaningful_update" in reasons:
        return "近期实现发生了有证据支持的实质更新，值得现在查看。"
    if "strong_recent_momentum" in reasons:
        return "连续观察显示关注正在明显增加，适合现在判断其长期价值是否成立。"
    return None


def _card(assessment: Any, profile: Any) -> SelectionServingCard:
    copy = assessment.copyResult
    delta = assessment.candidate.observedStarDelta
    hours = assessment.candidate.observedWindowHours
    momentum = None
    if delta is not None and hours is not None and delta > 0:
        momentum = f"已观察 {hours:g}h +{delta:,} Star"
    return SelectionServingCard(
        githubRepositoryId=assessment.candidate.githubRepositoryId,
        repository=assessment.candidate.repository,
        htmlUrl=assessment.candidate.htmlUrl,
        identitySummaryZh=copy.identitySummaryZh if copy else _fallback_identity(assessment, profile),
        corePositioningZh=(profile.positioningZh or profile.coreValueZh or profile.officialPositioningZh),
        whyWorthSeeingZh=(copy.whyWorthSeeingZh if copy else _REASON_COPY[assessment.primaryReason]),
        whyNowZh=copy.whyNowZh if copy and copy.whyNowZh else _why_now(assessment),
        primaryReason=assessment.primaryReason,
        supportingReasons=assessment.supportingReasons,
        category=assessment.category,
        categorySource=assessment.categorySource,
        productFormsZh=assessment.productFormsZh,
        primaryLanguage=assessment.candidate.primaryLanguage,
        topics=assessment.candidate.topics[:12],
        licenseSpdxId=assessment.candidate.licenseSpdxId,
        totalStars=assessment.candidate.totalStars,
        momentumLabel=momentum,
        reusableAssets=copy.reusableAssets if copy else [],
        bestFit=copy.bestFit if copy else [],
    )


def build_selection_serving(built: BuiltSelection) -> BuiltSelectionServing:
    artifact = built.artifact
    published = sorted(
        (item for item in artifact.assessments if item.publicationDisposition == "publish"),
        key=lambda item: item.displayOrder or 21,
    )
    cards: list[SelectionServingCard] = []
    contexts: dict[int, SelectionProjectContext] = {}
    for assessment in published:
        collected = built.profiles.profiles[assessment.candidate.githubRepositoryId]
        card = _card(assessment, collected.profile)
        cards.append(card)
        contexts[assessment.candidate.githubRepositoryId] = SelectionProjectContext(
            schemaVersion=1,
            selectionGenerationId=artifact.selectionGenerationId,
            sourceObservationSetId=artifact.sourceObservationSetId,
            generatedAt=artifact.generatedAt,
            card=card,
            selectionEvidenceDigest=assessment.selectionEvidenceDigest,
            timelinessReasonCodes=assessment.timeliness.reasonCodes,
            evidence=assessment.valueEvidence + assessment.timelinessEvidence + assessment.peerEvidence,
            canonicalProfile=collected.profile.model_dump(mode="json"),
            canonicalEvidence=collected.evidence.model_dump(mode="json"),
        )
    categories: dict[str, int] = {}
    reasons: dict[str, int] = {}
    for card in cards:
        categories[card.category] = categories.get(card.category, 0) + 1
        reasons[card.primaryReason] = reasons.get(card.primaryReason, 0) + 1
    snapshot = SelectionServingSnapshot(
        schemaVersion=1,
        selectionGenerationId=artifact.selectionGenerationId,
        sourceObservationSetId=artifact.sourceObservationSetId,
        generatedAt=artifact.generatedAt,
        latestCaptureId=artifact.latestCaptureId,
        latestCaptureAt=artifact.latestCaptureAt,
        sourceWindowStart=artifact.sourceWindowStart,
        sourceWindowEnd=artifact.sourceWindowEnd,
        status="empty" if not cards else "ready",
        items=cards,
        categoryCounts=categories,
        primaryReasonCounts=reasons,
        coverageLabelZh=(
            "基于 Rardar 多源候选召回与已验证 Observation 历史形成的本地精选；"
            "它不是对全部 GitHub 的完整扫描，也不按热度公开排名。"
        ),
        sourceCoverageState=artifact.sourceCoverageState,
        sourceTodayGeneration=artifact.todayGenerationId,
        candidateCount=artifact.universeCount,
        selectedCount=artifact.decisionCounts.get("SELECT_NOW", 0),
        publishedCount=artifact.publishedCount,
        suppressedCount=(
            artifact.publicationCounts.get("suppress_duplicate", 0)
            + artifact.publicationCounts.get("suppress_capacity", 0)
        ),
    )
    files: dict[str, bytes] = {
        "raw/selection.json": built.raw_bytes,
        "serving/selection.json": _canonical_bytes(snapshot),
    }
    for identifier, context in contexts.items():
        files[f"serving/projects/{identifier}.json"] = _canonical_bytes(context)
    inventory = [
        SelectionServingFile(path=path, sha256=_sha(raw), bytes=len(raw)) for path, raw in sorted(files.items())
    ]
    manifest = SelectionServingManifest(
        schemaVersion=1,
        state="ready",
        selectionGenerationId=artifact.selectionGenerationId,
        sourceObservationSetId=artifact.sourceObservationSetId,
        rawArtifactSha256=_sha(built.raw_bytes),
        generatedAt=artifact.generatedAt,
        files=inventory,
        projectIds=[card.githubRepositoryId for card in cards],
    )
    manifest_raw = _canonical_bytes(manifest)
    files["manifest.json"] = manifest_raw
    pointer = SelectionServingPointer(
        schemaVersion=1,
        selectionGenerationId=artifact.selectionGenerationId,
        sourceObservationSetId=artifact.sourceObservationSetId,
        manifestSha256=_sha(manifest_raw),
        activatedAt=artifact.generatedAt,
    )
    return BuiltSelectionServing(
        selection_generation_id=artifact.selectionGenerationId,
        source_observation_set_id=artifact.sourceObservationSetId,
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
        raise SelectionServingError("rardar_selection_unsafe_path", "Selection path is unsafe")


def _optional_bytes(path: Path) -> bytes | None:
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode) or _is_reparse(info):
        raise SelectionServingError("rardar_selection_unsafe_path", "Selection pointer is unsafe")
    return path.read_bytes()


def _atomic(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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


def _tree_matches(root: Path, files: dict[str, bytes]) -> bool:
    actual: set[str] = set()
    for path in root.rglob("*"):
        info = os.lstat(path)
        if stat.S_ISLNK(info.st_mode) or _is_reparse(info):
            raise SelectionServingError("rardar_selection_unsafe_path", "Selection generation is unsafe")
        if stat.S_ISREG(info.st_mode):
            actual.add(path.relative_to(root).as_posix())
        elif not stat.S_ISDIR(info.st_mode):
            raise SelectionServingError("rardar_selection_unsafe_path", "Selection generation is unsafe")
    if actual != set(files):
        return False
    safe = _SafeRoot(str(root))
    return all(safe.read_stable(path, maximum_bytes=max(1, len(raw))) == raw for path, raw in files.items())


def install_selection_serving(target: Path, built: BuiltSelectionServing) -> SelectionInstallResult:
    if not _ID.fullmatch(built.selection_generation_id):
        raise SelectionServingError("rardar_selection_invalid", "Selection generation ID is unsafe")
    store = target / _STORE
    generations = store / "generations"
    _ensure_plain(target)
    _ensure_plain(store)
    _ensure_plain(generations)
    final = generations / built.selection_generation_id
    created = False
    if final.exists():
        _ensure_plain(final)
        if not _tree_matches(final, built.files):
            raise SelectionServingError("rardar_selection_generation_conflict", "Immutable Selection differs")
    else:
        candidate = generations / f".{built.selection_generation_id}.candidate-{os.getpid()}"
        if candidate.exists():
            raise SelectionServingError("rardar_selection_generation_conflict", "Selection candidate exists")
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
        SelectionServingLoader(target).validate_generation(built.selection_generation_id)
    except Exception:
        if created:
            shutil.rmtree(final, ignore_errors=True)
        raise

    pointer_path = store / "current.json"
    previous = _optional_bytes(pointer_path)
    if previous == built.pointer_raw:
        return SelectionInstallResult(
            built.selection_generation_id,
            built.source_observation_set_id,
            built.manifest_sha256,
            created,
            False,
        )
    if previous is not None:
        try:
            SelectionServingLoader(target).load_with_etag()
        except Exception:
            if created:
                shutil.rmtree(final, ignore_errors=True)
            raise
    try:
        _atomic(pointer_path, built.pointer_raw)
        snapshot, _etag = SelectionServingLoader(target).load_with_etag()
        if snapshot.selectionGenerationId != built.selection_generation_id:
            raise SelectionServingError("rardar_selection_activation_failed", "Selection pointer did not activate")
    except Exception:
        if previous is None:
            pointer_path.unlink(missing_ok=True)
        else:
            _atomic(pointer_path, previous)
        if created:
            shutil.rmtree(final, ignore_errors=True)
        raise
    return SelectionInstallResult(
        built.selection_generation_id,
        built.source_observation_set_id,
        built.manifest_sha256,
        created,
        True,
    )


class SelectionServingLoader:
    def __init__(self, target: Path | str) -> None:
        self.target = Path(target)
        self.safe = _SafeRoot(str(self.target))

    def _read(self, relative: str, maximum: int) -> bytes:
        try:
            return self.safe.read_stable(relative, maximum_bytes=maximum)
        except (FileNotFoundError, OSError, ValueError) as exc:
            raise SelectionServingError("rardar_selection_invalid", "Selection read failed") from exc

    def _pointer(self) -> tuple[SelectionServingPointer, bytes]:
        try:
            raw = self.safe.read_stable(f"{_STORE}/current.json", maximum_bytes=64 * 1024)
        except FileNotFoundError as exc:
            raise SelectionServingError("rardar_selection_not_configured", "Selection is not built") from exc
        except ValueError as exc:
            raise SelectionServingError("rardar_selection_invalid", "Selection pointer path is unsafe") from exc
        except OSError as exc:
            raise SelectionServingError("rardar_selection_invalid", "Selection pointer read failed") from exc
        return _strict(raw, SelectionServingPointer, "rardar_selection_invalid"), raw

    def _manifest(self, generation: str, expected_sha: str | None = None) -> tuple[SelectionServingManifest, bytes]:
        if not _ID.fullmatch(generation):
            raise SelectionServingError("rardar_selection_invalid", "Selection generation ID is unsafe")
        raw = self._read(f"{_STORE}/generations/{generation}/manifest.json", 1024 * 1024)
        if expected_sha is not None and _sha(raw) != expected_sha:
            raise SelectionServingError("rardar_selection_invalid", "Selection manifest digest is invalid")
        manifest = _strict(raw, SelectionServingManifest, "rardar_selection_invalid")
        if manifest.selectionGenerationId != generation or manifest.state != "ready":
            raise SelectionServingError("rardar_selection_invalid", "Selection manifest identity is invalid")
        return manifest, raw

    def _file(self, generation: str, descriptor: SelectionServingFile) -> bytes:
        raw = self._read(f"{_STORE}/generations/{generation}/{descriptor.path}", descriptor.bytes)
        if len(raw) != descriptor.bytes or _sha(raw) != descriptor.sha256:
            raise SelectionServingError("rardar_selection_invalid", "Selection artifact digest is invalid")
        return raw

    def load_with_etag(self) -> tuple[SelectionServingSnapshot, str]:
        pointer, _pointer_raw = self._pointer()
        generation = pointer.selectionGenerationId
        manifest, _manifest_raw = self._manifest(generation, pointer.manifestSha256)
        descriptors = {item.path: item for item in manifest.files}
        raw = self._file(generation, descriptors["serving/selection.json"])
        snapshot = _strict(raw, SelectionServingSnapshot, "rardar_selection_invalid")
        if (
            snapshot.selectionGenerationId != generation
            or snapshot.sourceObservationSetId != pointer.sourceObservationSetId
            or manifest.sourceObservationSetId != pointer.sourceObservationSetId
            or [item.githubRepositoryId for item in snapshot.items] != manifest.projectIds
        ):
            raise SelectionServingError("rardar_selection_invalid", "Selection snapshot is mixed")
        return snapshot, f'"{pointer.manifestSha256}"'

    def load_project_with_etag(
        self, repository_id: int, selection_generation_id: str
    ) -> tuple[SelectionProjectContext, str]:
        if repository_id <= 0 or not _ID.fullmatch(selection_generation_id):
            raise SelectionServingError("rardar_selection_project_not_found", "Selection project identity is invalid")
        manifest, manifest_raw = self._manifest(selection_generation_id)
        if repository_id not in manifest.projectIds:
            raise SelectionServingError("rardar_selection_project_not_found", "Project is absent from Selection")
        descriptors = {item.path: item for item in manifest.files}
        descriptor = descriptors[f"serving/projects/{repository_id}.json"]
        raw = self._file(selection_generation_id, descriptor)
        context = _strict(raw, SelectionProjectContext, "rardar_selection_invalid")
        if (
            context.selectionGenerationId != selection_generation_id
            or context.sourceObservationSetId != manifest.sourceObservationSetId
            or context.card.githubRepositoryId != repository_id
        ):
            raise SelectionServingError("rardar_selection_invalid", "Selection project is mixed")
        return context, f'"{_sha(manifest_raw)}"'

    def load_artifact(self, generation: str | None = None) -> SelectionArtifact:
        if generation is None:
            pointer, _raw = self._pointer()
            generation = pointer.selectionGenerationId
            expected = pointer.manifestSha256
        else:
            expected = None
        manifest, _manifest_raw = self._manifest(generation, expected)
        descriptors = {item.path: item for item in manifest.files}
        raw = self._file(generation, descriptors["raw/selection.json"])
        if _sha(raw) != manifest.rawArtifactSha256:
            raise SelectionServingError("rardar_selection_invalid", "Selection raw binding is invalid")
        artifact = _strict(raw, SelectionArtifact, "rardar_selection_invalid")
        payload = artifact.model_dump(mode="json")
        digest = payload.pop("payloadDigest")
        if (
            artifact.selectionGenerationId != generation
            or artifact.sourceObservationSetId != manifest.sourceObservationSetId
            or _sha(_canonical_bytes(payload)) != digest
        ):
            raise SelectionServingError("rardar_selection_invalid", "Selection raw artifact is mixed")
        return artifact

    def validate_generation(self, generation: str | None = None) -> SelectionArtifact:
        artifact = self.load_artifact(generation)
        manifest, _raw = self._manifest(artifact.selectionGenerationId)
        descriptors = {item.path: item for item in manifest.files}
        generation_root = self.target / _STORE / "generations" / artifact.selectionGenerationId
        expected_paths = {"manifest.json", *descriptors}
        actual_paths: set[str] = set()
        for path in generation_root.rglob("*"):
            info = os.lstat(path)
            if stat.S_ISLNK(info.st_mode) or _is_reparse(info):
                raise SelectionServingError("rardar_selection_unsafe_path", "Selection generation is unsafe")
            if stat.S_ISREG(info.st_mode):
                actual_paths.add(path.relative_to(generation_root).as_posix())
            elif not stat.S_ISDIR(info.st_mode):
                raise SelectionServingError("rardar_selection_unsafe_path", "Selection generation is unsafe")
        if actual_paths != expected_paths:
            raise SelectionServingError("rardar_selection_invalid", "Selection inventory is invalid")
        snapshot_raw = self._file(artifact.selectionGenerationId, descriptors["serving/selection.json"])
        snapshot = _strict(snapshot_raw, SelectionServingSnapshot, "rardar_selection_invalid")
        if snapshot.selectionGenerationId != artifact.selectionGenerationId:
            raise SelectionServingError("rardar_selection_invalid", "Selection serving/raw identity differs")
        for identifier in manifest.projectIds:
            context_raw = self._file(
                artifact.selectionGenerationId,
                descriptors[f"serving/projects/{identifier}.json"],
            )
            context = _strict(context_raw, SelectionProjectContext, "rardar_selection_invalid")
            if context.card.githubRepositoryId != identifier:
                raise SelectionServingError("rardar_selection_invalid", "Selection context identity differs")
        return artifact


def rollback_selection(target: Path, generation: str) -> SelectionInstallResult:
    loader = SelectionServingLoader(target)
    artifact = loader.validate_generation(generation)
    manifest, manifest_raw = loader._manifest(generation)
    pointer = SelectionServingPointer(
        schemaVersion=1,
        selectionGenerationId=generation,
        sourceObservationSetId=manifest.sourceObservationSetId,
        manifestSha256=_sha(manifest_raw),
        activatedAt=datetime.now(UTC),
    )
    pointer_raw = _canonical_bytes(pointer)
    current = target / _STORE / "current.json"
    previous = _optional_bytes(current)
    try:
        _atomic(current, pointer_raw)
        loaded, _etag = loader.load_with_etag()
        if loaded.selectionGenerationId != generation:
            raise SelectionServingError("rardar_selection_rollback_failed", "Selection rollback did not activate")
    except Exception:
        if previous is None:
            current.unlink(missing_ok=True)
        else:
            _atomic(current, previous)
        raise
    return SelectionInstallResult(
        selection_generation_id=artifact.selectionGenerationId,
        source_observation_set_id=artifact.sourceObservationSetId,
        manifest_sha256=_sha(manifest_raw),
        created=False,
        changed=previous != pointer_raw,
    )


__all__ = [
    "BuiltSelectionServing",
    "SelectionInstallResult",
    "SelectionServingError",
    "SelectionServingLoader",
    "build_selection_serving",
    "install_selection_serving",
    "rollback_selection",
]
