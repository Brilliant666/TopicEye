"""Build, atomically publish, and safely load the Rardar Discover projection."""

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
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.integrations.rardar.adapter import RardarArtifactError, _SafeRoot, _strict_json
from app.integrations.rardar.discover import DiscoverBoard, DiscoverItem, LoadedDiscoverArtifact
from app.integrations.rardar.discover_serving_schemas import (
    DiscoverProfileSummary,
    DiscoverProjectDetail,
    DiscoverServingCard,
    DiscoverServingFile,
    DiscoverServingManifest,
    DiscoverServingPointer,
    DiscoverServingProjectRecord,
    DiscoverServingSnapshot,
)
from app.integrations.rardar.schemas import ExactExplosionProject
from app.integrations.rardar.serving import ProfileProvider
from app.integrations.rardar.serving_profiles import (
    ProfileBuildResult,
    _profile_is_publishable,
)
from app.integrations.rardar.serving_schemas import ProjectEvidenceProjection

_STORE = "discover-serving"
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,190}$")
_SOURCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,126}$")
_REPARSE_POINT = 0x400
DISCOVER_SERVING_PROJECTION_VERSION = 5
_CATEGORY_PRIORITY = ("video-content", "ai-agent", "data-infra", "dev-tools", "productivity")
_CATEGORY_TERMS = {
    "ai-agent": (
        "agent",
        "artificial intelligence",
        "人工智能",
        "llm",
        "large language model",
        "machine learning",
        "机器学习",
        "inference",
        "模型",
        "mcp",
    ),
    "dev-tools": (
        "developer tool",
        "开发工具",
        "sdk",
        "cli",
        "command line",
        "framework",
        "library",
        "ide",
        "compiler",
        "api client",
    ),
    "data-infra": (
        "database",
        "数据库",
        "data infrastructure",
        "数据基础设施",
        "kubernetes",
        "observability",
        "vector database",
        "data pipeline",
        "distributed system",
        "storage",
    ),
    "productivity": (
        "productivity",
        "生产力",
        "workflow",
        "工作流",
        "automation",
        "自动化",
        "note",
        "knowledge",
        "read it later",
        "terminal",
    ),
    "video-content": (
        "video",
        "视频",
        "content creator",
        "内容创作",
        "media",
        "multimedia",
        "audio",
        "image generation",
        "streaming",
        "ffmpeg",
    ),
}


class DiscoverServingError(RardarArtifactError):
    pass


@dataclass(frozen=True)
class BuiltDiscoverServing:
    serving_generation_id: str
    discover_generation_id: str
    manifest_sha256: str
    pointer_raw: bytes
    files: dict[str, bytes]
    profile_result: ProfileBuildResult
    profile_summary: DiscoverProfileSummary


@dataclass(frozen=True)
class DiscoverServingInstallResult:
    serving_generation_id: str
    discover_generation_id: str
    manifest_sha256: str
    created: bool
    changed: bool


@dataclass
class _Bundle:
    pointer_sha256: str
    pointer: DiscoverServingPointer
    manifest: DiscoverServingManifest
    snapshot: DiscoverServingSnapshot
    details: dict[int, DiscoverProjectDetail]


_CACHE_LOCK = threading.RLock()
_CURRENT_CACHE: dict[str, _Bundle] = {}
_SOURCE_CACHE: dict[tuple[str, str], _Bundle] = {}


@dataclass(frozen=True)
class _CategoryProjection:
    category: str
    source_mode: str
    evidence_refs: tuple[str, ...]


def clear_discover_serving_cache() -> None:
    with _CACHE_LOCK:
        _CURRENT_CACHE.clear()
        _SOURCE_CACHE.clear()


def _canonical_bytes(value: object) -> bytes:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return (
        json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _as_profile_project(item: DiscoverItem, source: LoadedDiscoverArtifact, rank: int) -> ExactExplosionProject:
    metadata = source.projects[item.githubRepositoryId]
    return ExactExplosionProject.model_validate_json(
        _canonical_bytes(
            {
                "rank": rank,
                "githubRepositoryId": item.githubRepositoryId,
                "repository": item.repository,
                "htmlUrl": str(item.url),
                "totalStars": item.totalStars,
                "baselineStars": max(0, item.totalStars - item.observedStarDelta),
                "observedStarDelta": item.observedStarDelta,
                "windowStartedAt": item.observedWindowStart.isoformat(),
                "windowEndedAt": item.observedWindowEnd.isoformat(),
                "primaryLanguage": item.language,
                "topics": item.topics,
                "description": metadata.description,
                "forks": metadata.forks,
                "pushedAt": item.latestPushAt.isoformat() if item.latestPushAt else None,
                "defaultBranch": metadata.default_branch,
                "licenseSpdxId": item.license,
                "archived": item.isArchived,
                "fork": item.isFork,
                "mirrorUrl": None,
                "state": "exact_window",
            }
        ),
        strict=True,
    )


def _selected(board: DiscoverBoard) -> list[DiscoverItem]:
    return [
        *board.justDiscovered[:10],
        *board.outsideTodayMomentum[:10],
        *board.rising[:10],
        *board.nearValidation[:10],
    ]


def _complete_profile(profile: Any, evidence: Any) -> bool:
    return bool(
        _profile_is_publishable(profile)
        and profile.officialNarrativeMode in {"official_zh", "official_translated", "rardar_derived"}
        and profile.qualityState != "rejected"
        and profile.identitySummaryZh
        and profile.positioningZh
        and profile.positioningEvidenceRefs
        and profile.capabilities
        and all(capability.sourceMode is not None and capability.evidenceRefs for capability in profile.capabilities)
        and set(profile.positioningEvidenceRefs).issubset(evidence.evidenceIndex)
        and all(set(capability.evidenceRefs).issubset(evidence.evidenceIndex) for capability in profile.capabilities)
    )


def _category_projection(item: DiscoverItem, profile: Any) -> _CategoryProjection:
    signals: list[tuple[str, str, str]] = []
    for index, value in enumerate(profile.productFormsZh):
        signals.append((value, f"profile.productFormsZh[{index}]", "canonical_profile"))
    for index, value in enumerate(profile.primaryUseCasesZh):
        signals.append((value, f"profile.primaryUseCasesZh[{index}]", "canonical_profile"))
    for index, value in enumerate(profile.deliveryFormsZh):
        signals.append((value, f"profile.deliveryFormsZh[{index}]", "canonical_profile"))
    signals.append((profile.positioningZh or "", "profile.positioningZh", "canonical_profile"))
    for index, capability in enumerate(profile.capabilities):
        signals.append(
            (
                f"{capability.title} {capability.detail}",
                capability.evidenceRefs[0] if capability.evidenceRefs else f"profile.capabilities[{index}]",
                "canonical_profile",
            )
        )
    for index, topic in enumerate(item.topics):
        signals.append((topic.replace("-", " "), f"github.topics[{index}]", "github_metadata"))
    if item.language:
        signals.append((item.language, "github.primaryLanguage", "github_metadata"))

    matches: dict[str, list[tuple[str, str]]] = {category: [] for category in _CATEGORY_TERMS}
    for text, reference, source_mode in signals:
        normalized = " ".join(text.casefold().replace("_", " ").split())
        if not normalized:
            continue
        for category, terms in _CATEGORY_TERMS.items():
            if any(term in normalized for term in terms):
                matches[category].append((reference, source_mode))
    selected = max(
        _CATEGORY_PRIORITY, key=lambda category: (len(matches[category]), -_CATEGORY_PRIORITY.index(category))
    )
    if not matches[selected]:
        return _CategoryProjection("other", "deterministic_fallback", ("profile.no_category_signal",))
    references = tuple(dict.fromkeys(reference for reference, _ in matches[selected]))[:8]
    source_mode = (
        "canonical_profile" if any(mode == "canonical_profile" for _, mode in matches[selected]) else "github_metadata"
    )
    return _CategoryProjection(selected, source_mode, references)


def _profile_summary(result: ProfileBuildResult, count: int, category_count: int) -> DiscoverProfileSummary:
    profiles = [value.profile for value in result.profiles.values()]
    evidence = [value.evidence for value in result.profiles.values()]
    complete = sum(_complete_profile(profile, item) for profile, item in zip(profiles, evidence, strict=True))
    return DiscoverProfileSummary(
        selectedCount=count,
        identityComplete=complete,
        positioningComplete=complete,
        capabilitiesComplete=complete,
        categoryComplete=category_count,
        officialZh=sum(profile.officialNarrativeMode == "official_zh" for profile in profiles),
        officialTranslated=sum(profile.officialNarrativeMode == "official_translated" for profile in profiles),
        rardarDerived=sum(profile.officialNarrativeMode == "rardar_derived" for profile in profiles),
        githubRequests=result.github_requests,
        readmeCacheHits=result.readme_cache_hits,
        translationCalls=result.translation_calls,
        translationCacheHits=result.translation_cache_hits,
    )


def _card(
    item: DiscoverItem,
    profile: Any,
    category: _CategoryProjection | None,
) -> DiscoverServingCard:
    category_fields = (
        {
            "category": category.category,
            "categorySourceMode": category.source_mode,
            "categoryEvidenceRefs": list(category.evidence_refs),
        }
        if category is not None
        else {}
    )
    return DiscoverServingCard.model_validate_json(
        _canonical_bytes(
            item.model_dump(mode="json")
            | {
                "identitySummaryZh": profile.identitySummaryZh,
                "positioningZh": profile.positioningZh,
                "capabilities": [value.model_dump(mode="json") for value in profile.capabilities[:6]],
                "sourceMode": profile.officialNarrativeMode,
                "qualityState": profile.qualityState,
            }
            | category_fields
        ),
        strict=True,
    )


def _next_today_settlement(reference: datetime) -> datetime:
    zone = ZoneInfo("Asia/Shanghai")
    local = reference.astimezone(zone)
    candidate = local.replace(hour=8, minute=0, second=0, microsecond=0)
    if candidate <= local:
        candidate += timedelta(days=1)
    return candidate.astimezone(UTC)


def _today_reason(stage: str) -> str:
    return {
        "just_discovered": "new_candidate",
        "outside_today_momentum": "outside_today_top20_with_momentum",
        "rising": "awaiting_growth_evidence",
        "near_validation": "awaiting_daily_settlement",
    }[stage]


def build_discover_serving(
    source: LoadedDiscoverArtifact,
    *,
    cache_root: Path,
    profile_provider: ProfileProvider,
    synced_at: datetime | None = None,
    source_host: str | None = None,
) -> BuiltDiscoverServing:
    board = source.board
    publication_time = synced_at or board.generatedAt
    selected = _selected(board)
    profile_projects = [_as_profile_project(item, source, index) for index, item in enumerate(selected, start=1)]
    result = profile_provider(profile_projects, board.discoverGenerationId, cache_root)
    if set(result.profiles) != {item.githubRepositoryId for item in selected}:
        raise DiscoverServingError("rardar_discover_profile_incomplete", "Discover profile inventory is incomplete")
    for item in selected:
        collected = result.profiles[item.githubRepositoryId]
        if not _complete_profile(collected.profile, collected.evidence):
            raise DiscoverServingError(
                "rardar_discover_profile_incomplete",
                "Every published Discover item requires a complete static profile",
            )
    categories = {
        item.githubRepositoryId: _category_projection(item, result.profiles[item.githubRepositoryId].profile)
        for item in selected
    }
    summary = _profile_summary(result, len(selected), len(categories))
    profile_fingerprint = _sha(
        _canonical_bytes(
            {
                "projectionVersion": DISCOVER_SERVING_PROJECTION_VERSION,
                "projects": [
                    {
                        "id": item.githubRepositoryId,
                        "profile": result.profiles[item.githubRepositoryId].profile.model_dump(mode="json"),
                        "evidence": result.profiles[item.githubRepositoryId].evidence.model_dump(mode="json"),
                    }
                    for item in selected
                ],
            }
        )
    )
    serving_id = f"{board.discoverGenerationId}--{profile_fingerprint[:16]}"
    if not _ID.fullmatch(serving_id):
        raise DiscoverServingError("rardar_discover_serving_invalid", "Discover Serving identity is unsafe")

    serving_schema_version = 3 if board.schemaVersion == 3 else 2
    cards = {"justDiscovered": [], "outsideTodayMomentum": [], "rising": [], "nearValidation": []}
    files: dict[str, bytes] = {}
    for item in selected:
        collected = result.profiles[item.githubRepositoryId]
        category = categories[item.githubRepositoryId]
        card = _card(item, collected.profile, category)
        key = {
            "just_discovered": "justDiscovered",
            "outside_today_momentum": "outsideTodayMomentum",
            "rising": "rising",
            "near_validation": "nearValidation",
        }[item.stage]
        cards[key].append(card)
        record = DiscoverServingProjectRecord(
            schemaVersion=serving_schema_version,
            servingGenerationId=serving_id,
            discoverGenerationId=board.discoverGenerationId,
            facts=item,
            profile=collected.profile,
            category=category.category,
            categorySourceMode=category.source_mode,
            categoryEvidenceRefs=list(category.evidence_refs),
        )
        files[f"projects/{item.githubRepositoryId}.json"] = _canonical_bytes(record)
        files[f"evidence/{item.githubRepositoryId}.json"] = _canonical_bytes(collected.evidence)

    snapshot = DiscoverServingSnapshot(
        schemaVersion=serving_schema_version,
        servingGenerationId=serving_id,
        discoverGenerationId=board.discoverGenerationId,
        generatedAt=board.generatedAt,
        latestCaptureId=board.latestCaptureId,
        latestCaptureAt=board.latestCaptureCapturedAt,
        nextExpectedAt=board.latestCaptureScheduledAt + timedelta(minutes=board.updateCadenceMinutes),
        updateCadenceMinutes=120,
        stageCounts=board.stageCounts,
        justDiscovered=cards["justDiscovered"],
        outsideTodayMomentum=cards["outsideTodayMomentum"],
        rising=cards["rising"],
        nearValidation=cards["nearValidation"],
        coverage=board.coverage,
        conflictCount=board.conflictCount,
        conflictReasons=board.conflictReasons,
        todayExplosionGenerationId=board.todayExplosionGenerationId,
        sourceWindowStart=board.sourceWindowStart,
        sourceWindowEnd=board.sourceWindowEnd,
        sourceCaptureCount=board.sourceCaptureCount,
        sourceManifestSha256=source.manifest_sha256,
        sourceArtifactSha256=source.artifact_sha256,
        syncedAt=synced_at,
        sourceHost=source_host,
        profileSummary=summary,
        sourceSchemaVersion=board.schemaVersion,
        sourcePolicyVersion=board.policyVersion,
        suppressionSummary=board.suppressionSummary,
        todayPublishedTopCount=board.todayPublishedTopCount,
        eligibilitySummary=(
            {
                "observationCandidates": board.coverage.candidateCount,
                "todayExactFacts": board.todayExactCount,
                "todayPublished": board.todayPublishedCount,
                "excludedPublished": board.excludedPublishedCount,
                "exactOutsidePublishedEvaluated": board.exactOutsidePublishedEvaluatedCount,
                "preExactEvaluated": board.preExactEvaluatedCount,
                "invalid": board.eligibilityCounts.invalid if board.eligibilityCounts else None,
                "published": board.coverage.publishedCount,
                "suppressed": board.suppressionSummary.suppressedSignalCount,
            }
            if board.schemaVersion == 3 and board.eligibilityCounts is not None
            else None
        ),
    )
    files["discover.json"] = _canonical_bytes(snapshot)
    inventory = [
        DiscoverServingFile(path=path, sha256=_sha(raw), bytes=len(raw)) for path, raw in sorted(files.items())
    ]
    manifest = DiscoverServingManifest(
        schemaVersion=serving_schema_version,
        generationId=serving_id,
        discoverGenerationId=board.discoverGenerationId,
        createdAt=publication_time,
        state="ready",
        sourceManifestSha256=source.manifest_sha256,
        sourceArtifactSha256=source.artifact_sha256,
        files=inventory,
        projectIds=[item.githubRepositoryId for item in selected],
        profileSummary=summary,
    )
    manifest_raw = _canonical_bytes(manifest)
    files["manifest.json"] = manifest_raw
    pointer = DiscoverServingPointer(
        schemaVersion=serving_schema_version,
        generationId=serving_id,
        discoverGenerationId=board.discoverGenerationId,
        publishedAt=publication_time,
        previousGenerationId=None,
        manifestSha256=_sha(manifest_raw),
    )
    built = BuiltDiscoverServing(
        serving_generation_id=serving_id,
        discover_generation_id=board.discoverGenerationId,
        manifest_sha256=_sha(manifest_raw),
        pointer_raw=_canonical_bytes(pointer),
        files=files,
        profile_result=result,
        profile_summary=summary,
    )
    _validate_built(built)
    return built


def _strict(raw: bytes, model: type[Any], code: str) -> Any:
    try:
        _strict_json(raw)
        return model.model_validate_json(raw, strict=True)
    except Exception as exc:
        raise DiscoverServingError(code, "Discover Serving data failed strict validation") from exc


def _validate_built(built: BuiltDiscoverServing) -> None:
    manifest_raw = built.files["manifest.json"]
    manifest = _strict(manifest_raw, DiscoverServingManifest, "rardar_discover_serving_invalid")
    if _sha(manifest_raw) != built.manifest_sha256:
        raise DiscoverServingError("rardar_discover_serving_invalid", "Discover Serving manifest digest is invalid")
    declared = {item.path: item for item in manifest.files}
    actual = {key for key in built.files if key != "manifest.json"}
    if set(declared) != actual:
        raise DiscoverServingError("rardar_discover_serving_invalid", "Discover Serving inventory is incomplete")
    for path, entry in declared.items():
        raw = built.files[path]
        if _sha(raw) != entry.sha256 or len(raw) != entry.bytes:
            raise DiscoverServingError("rardar_discover_serving_invalid", "Discover Serving file digest is invalid")
    snapshot = _strict(built.files["discover.json"], DiscoverServingSnapshot, "rardar_discover_serving_invalid")
    if (
        snapshot.servingGenerationId != manifest.generationId
        or snapshot.discoverGenerationId != manifest.discoverGenerationId
    ):
        raise DiscoverServingError("rardar_discover_serving_invalid", "Discover Serving generation is mixed")
    cards = {
        item.githubRepositoryId: item
        for group in (
            snapshot.justDiscovered,
            snapshot.outsideTodayMomentum,
            snapshot.rising,
            snapshot.nearValidation,
        )
        for item in group
    }
    if list(cards) != manifest.projectIds:
        raise DiscoverServingError("rardar_discover_serving_invalid", "Discover Serving order is inconsistent")
    for identifier in manifest.projectIds:
        record = _strict(
            built.files[f"projects/{identifier}.json"],
            DiscoverServingProjectRecord,
            "rardar_discover_serving_invalid",
        )
        evidence = _strict(
            built.files[f"evidence/{identifier}.json"],
            ProjectEvidenceProjection,
            "rardar_discover_serving_invalid",
        )
        card = cards[identifier]
        card_facts = DiscoverItem.model_validate_json(
            _canonical_bytes(card.model_dump(mode="json", include=set(DiscoverItem.model_fields))),
            strict=True,
        )
        if record.facts != card_facts:
            raise DiscoverServingError(
                "rardar_discover_serving_invalid", "Discover card facts differ from detail facts"
            )
        if record.profile.evidenceDigest != evidence.digest or not _complete_profile(record.profile, evidence):
            raise DiscoverServingError(
                "rardar_discover_profile_incomplete", "Discover profile/evidence binding is invalid"
            )
        category = (
            _CategoryProjection(record.category, record.categorySourceMode, tuple(record.categoryEvidenceRefs))
            if record.category is not None and record.categorySourceMode is not None
            else None
        )
        expected_card = _card(record.facts, record.profile, category)
        if expected_card != card:
            raise DiscoverServingError("rardar_discover_serving_invalid", "Discover card profile differs from detail")


def _is_reparse(info: os.stat_result) -> bool:
    return bool(getattr(info, "st_file_attributes", 0) & _REPARSE_POINT)


def _ensure_plain(path: Path) -> None:
    if not path.is_absolute():
        raise DiscoverServingError("rardar_discover_serving_unsafe_path", "Discover Serving path must be absolute")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            with suppress(FileExistsError):
                current.mkdir()
            info = os.lstat(current)
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or _is_reparse(info):
            raise DiscoverServingError("rardar_discover_serving_unsafe_path", "Discover Serving path is unsafe")


def _tree_matches(root: Path, files: dict[str, bytes]) -> bool:
    actual: set[str] = set()
    for path in root.rglob("*"):
        info = os.lstat(path)
        if stat.S_ISLNK(info.st_mode) or _is_reparse(info):
            raise DiscoverServingError("rardar_discover_serving_unsafe_path", "Discover Serving generation is unsafe")
        if stat.S_ISREG(info.st_mode):
            actual.add(path.relative_to(root).as_posix())
        elif not stat.S_ISDIR(info.st_mode):
            raise DiscoverServingError("rardar_discover_serving_unsafe_path", "Discover Serving generation is unsafe")
    if actual != set(files):
        return False
    safe = _SafeRoot(str(root))
    return all(safe.read_stable(relative, maximum_bytes=max(len(raw), 1)) == raw for relative, raw in files.items())


def _optional_bytes(path: Path) -> bytes | None:
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode) or _is_reparse(info):
        raise DiscoverServingError("rardar_discover_serving_unsafe_path", "Discover Serving pointer is unsafe")
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


def install_discover_serving(target: Path, built: BuiltDiscoverServing) -> DiscoverServingInstallResult:
    _validate_built(built)
    store = target / _STORE
    _ensure_plain(target)
    _ensure_plain(store)
    generations = store / "generations"
    sources = store / "sources"
    _ensure_plain(generations)
    _ensure_plain(sources)
    final = generations / built.serving_generation_id
    created = False
    if final.exists():
        _ensure_plain(final)
        if not _tree_matches(final, built.files):
            raise DiscoverServingError(
                "rardar_discover_serving_generation_conflict", "Immutable Discover Serving differs"
            )
    else:
        candidate = generations / f".{built.serving_generation_id}.candidate-{os.getpid()}"
        if candidate.exists():
            raise DiscoverServingError(
                "rardar_discover_serving_generation_conflict", "Discover Serving candidate exists"
            )
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

    current_path = store / "current.json"
    source_path = sources / f"{built.discover_generation_id}.json"
    old_current = _optional_bytes(current_path)
    old_source = _optional_bytes(source_path)
    previous = None
    if old_current:
        try:
            old_pointer = DiscoverServingPointer.model_validate_json(old_current, strict=True)
        except Exception as exc:
            raise DiscoverServingError(
                "rardar_discover_serving_current_invalid",
                "Existing Discover Serving pointer is invalid",
            ) from exc
        try:
            DiscoverServingLoader(target).load_with_etag()
        except DiscoverServingError as exc:
            # A stricter profile projection may intentionally invalidate the
            # previous generation after its pointer, manifest, hashes, schema,
            # and identity bindings have already passed validation. A complete
            # replacement is the recovery path; every other integrity failure
            # remains fail-closed.
            if exc.code != "rardar_discover_profile_incomplete":
                raise
        previous = old_pointer.generationId
        if (
            old_pointer.generationId == built.serving_generation_id
            and old_pointer.discoverGenerationId == built.discover_generation_id
            and old_pointer.manifestSha256 == built.manifest_sha256
        ):
            if old_source is None:
                _atomic(source_path, old_current)
                clear_discover_serving_cache()
                return DiscoverServingInstallResult(
                    serving_generation_id=built.serving_generation_id,
                    discover_generation_id=built.discover_generation_id,
                    manifest_sha256=built.manifest_sha256,
                    created=created,
                    changed=True,
                )
            if old_source == old_current:
                return DiscoverServingInstallResult(
                    serving_generation_id=built.serving_generation_id,
                    discover_generation_id=built.discover_generation_id,
                    manifest_sha256=built.manifest_sha256,
                    created=created,
                    changed=False,
                )
            raise DiscoverServingError(
                "rardar_discover_serving_source_conflict",
                "Existing Discover source pointer differs from current",
            )
    pointer = DiscoverServingPointer.model_validate_json(built.pointer_raw, strict=True).model_copy(
        update={"previousGenerationId": previous}
    )
    pointer_raw = _canonical_bytes(pointer)
    changed = old_current != pointer_raw or old_source != pointer_raw
    try:
        _atomic(source_path, pointer_raw)
        _atomic(current_path, pointer_raw)
        clear_discover_serving_cache()
        loaded, _ = DiscoverServingLoader(target).load_with_etag()
        if loaded.discoverGenerationId != built.discover_generation_id:
            raise DiscoverServingError("rardar_discover_serving_activation_failed", "Discover Serving did not activate")
    except Exception:
        if old_current is None:
            current_path.unlink(missing_ok=True)
        else:
            _atomic(current_path, old_current)
        if old_source is None:
            source_path.unlink(missing_ok=True)
        else:
            _atomic(source_path, old_source)
        clear_discover_serving_cache()
        if created:
            shutil.rmtree(final, ignore_errors=True)
        raise
    return DiscoverServingInstallResult(
        serving_generation_id=built.serving_generation_id,
        discover_generation_id=built.discover_generation_id,
        manifest_sha256=built.manifest_sha256,
        created=created,
        changed=changed,
    )


class DiscoverServingLoader:
    def __init__(self, target: Path | str) -> None:
        self.target = Path(target)
        self.safe = _SafeRoot(str(self.target))

    def _read(self, relative: str, maximum: int) -> bytes:
        try:
            return self.safe.read_stable(relative, maximum_bytes=maximum)
        except (FileNotFoundError, OSError, ValueError) as exc:
            raise DiscoverServingError("rardar_discover_serving_invalid", "Discover Serving read failed") from exc

    def _bundle(self, pointer_relative: str, source_id: str | None = None) -> _Bundle:
        self.safe.ensure_available()
        try:
            pointer_raw = self.safe.read_stable(pointer_relative, maximum_bytes=64 * 1024)
        except FileNotFoundError as exc:
            code = (
                "rardar_discover_not_configured"
                if pointer_relative == f"{_STORE}/current.json"
                else "rardar_discover_project_not_found"
            )
            raise DiscoverServingError(code, "Discover Serving pointer is unavailable") from exc
        pointer = _strict(pointer_raw, DiscoverServingPointer, "rardar_discover_serving_invalid")
        if source_id is not None and pointer.discoverGenerationId != source_id:
            raise DiscoverServingError("rardar_discover_revision_mismatch", "Discover Serving source pointer is mixed")
        cache_key = str(self.target)
        pointer_sha = _sha(pointer_raw)
        generation = pointer.generationId
        if not _ID.fullmatch(generation):
            raise DiscoverServingError("rardar_discover_serving_invalid", "Discover Serving generation ID is unsafe")
        base = f"{_STORE}/generations/{generation}"
        manifest_raw = self._read(f"{base}/manifest.json", 1024 * 1024)
        if _sha(manifest_raw) != pointer.manifestSha256:
            raise DiscoverServingError("rardar_discover_serving_invalid", "Discover Serving manifest digest is invalid")
        manifest = _strict(manifest_raw, DiscoverServingManifest, "rardar_discover_serving_invalid")
        if manifest.generationId != generation or manifest.discoverGenerationId != pointer.discoverGenerationId:
            raise DiscoverServingError("rardar_discover_serving_invalid", "Discover Serving generation is mixed")
        files: dict[str, bytes] = {"manifest.json": manifest_raw}
        for item in manifest.files:
            raw = self._read(f"{base}/{item.path}", item.bytes)
            if len(raw) != item.bytes or _sha(raw) != item.sha256:
                raise DiscoverServingError(
                    "rardar_discover_serving_invalid", "Discover Serving artifact digest is invalid"
                )
            files[item.path] = raw
        snapshot = _strict(files["discover.json"], DiscoverServingSnapshot, "rardar_discover_serving_invalid")
        if (
            snapshot.servingGenerationId != generation
            or snapshot.discoverGenerationId != pointer.discoverGenerationId
            or snapshot.profileSummary != manifest.profileSummary
            or snapshot.sourceManifestSha256 != manifest.sourceManifestSha256
            or snapshot.sourceArtifactSha256 != manifest.sourceArtifactSha256
        ):
            raise DiscoverServingError("rardar_discover_serving_invalid", "Discover Serving snapshot is mixed")
        cards = {
            item.githubRepositoryId: item
            for group in (
                snapshot.justDiscovered,
                snapshot.outsideTodayMomentum,
                snapshot.rising,
                snapshot.nearValidation,
            )
            for item in group
        }
        if list(cards) != manifest.projectIds:
            raise DiscoverServingError("rardar_discover_serving_invalid", "Discover Serving item order is invalid")
        details: dict[int, DiscoverProjectDetail] = {}
        for identifier in manifest.projectIds:
            record = _strict(
                files[f"projects/{identifier}.json"], DiscoverServingProjectRecord, "rardar_discover_serving_invalid"
            )
            evidence = _strict(
                files[f"evidence/{identifier}.json"], ProjectEvidenceProjection, "rardar_discover_serving_invalid"
            )
            if record.servingGenerationId != generation or record.discoverGenerationId != pointer.discoverGenerationId:
                raise DiscoverServingError("rardar_discover_serving_invalid", "Discover project generation is mixed")
            category = (
                _CategoryProjection(record.category, record.categorySourceMode, tuple(record.categoryEvidenceRefs))
                if record.category is not None and record.categorySourceMode is not None
                else None
            )
            if _card(record.facts, record.profile, category) != cards.get(identifier) or not _complete_profile(
                record.profile, evidence
            ):
                raise DiscoverServingError("rardar_discover_profile_incomplete", "Discover project profile is invalid")
            details[identifier] = DiscoverProjectDetail(
                schemaVersion=record.schemaVersion,
                servingGenerationId=generation,
                discoverGenerationId=pointer.discoverGenerationId,
                facts=record.facts,
                profile=record.profile,
                evidence=evidence,
                coverage=snapshot.coverage,
                conflictCount=snapshot.conflictCount,
                category=record.category,
                categorySourceMode=record.categorySourceMode,
                categoryEvidenceRefs=record.categoryEvidenceRefs,
                nextExpectedAt=snapshot.nextExpectedAt if record.schemaVersion in {2, 3} else None,
                nextTodaySettlementAt=(
                    _next_today_settlement(snapshot.latestCaptureAt) if record.schemaVersion in {2, 3} else None
                ),
                todayStatus=(
                    "outside_today_top20"
                    if record.schemaVersion == 3 and record.facts.stage == "outside_today_momentum"
                    else "not_in_source_today"
                    if record.schemaVersion in {2, 3}
                    else None
                ),
                todayReason=_today_reason(record.facts.stage) if record.schemaVersion in {2, 3} else None,
                todayPublishedTopCount=snapshot.todayPublishedTopCount if record.schemaVersion == 3 else None,
            )
        bundle = _Bundle(pointer_sha, pointer, manifest, snapshot, details)
        if source_id is None:
            _CURRENT_CACHE[cache_key] = bundle
        else:
            _SOURCE_CACHE[(cache_key, source_id)] = bundle
        return bundle

    def load_with_etag(self) -> tuple[DiscoverServingSnapshot, str]:
        with _CACHE_LOCK:
            bundle = self._bundle(f"{_STORE}/current.json")
            return bundle.snapshot, f'"{bundle.pointer.manifestSha256}"'

    def load_project_with_etag(
        self, repository_id: int, discover_generation_id: str
    ) -> tuple[DiscoverProjectDetail, str]:
        if repository_id <= 0 or not _SOURCE_ID.fullmatch(discover_generation_id):
            raise DiscoverServingError("rardar_discover_project_not_found", "Discover project identity is invalid")
        with _CACHE_LOCK:
            bundle = self._bundle(
                f"{_STORE}/sources/{discover_generation_id}.json",
                source_id=discover_generation_id,
            )
            detail = bundle.details.get(repository_id)
            if detail is None:
                raise DiscoverServingError("rardar_discover_project_not_found", "Project is absent from Discover")
            return detail, f'"{bundle.pointer.manifestSha256}"'


__all__ = [
    "BuiltDiscoverServing",
    "DiscoverServingError",
    "DiscoverServingLoader",
    "build_discover_serving",
    "clear_discover_serving_cache",
    "install_discover_serving",
]
