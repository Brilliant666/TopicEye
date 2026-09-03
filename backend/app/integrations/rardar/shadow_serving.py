"""Independent immutable local Shadow pointer; no full Selection activation."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from collections import Counter
from pathlib import Path

from app.integrations.rardar.adapter import RardarArtifactError, _SafeRoot, _strict_json
from app.integrations.rardar.selection_schemas import SelectionApiResponse, SelectionProjectContext
from app.integrations.rardar.shadow_schemas import ShadowReviewArtifact
from app.services.llm.provider_budget import ProviderBudgetError, atomic, canonical, file_lock, plain

STORE = "discover-shadow-review"
_GENERATION = re.compile(r"^shadow-[a-f0-9]{32}$")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def projection(artifact: ShadowReviewArtifact) -> SelectionApiResponse:
    cards = artifact.previewItems
    return SelectionApiResponse(
        mode="shadow",
        status="degraded",
        state="degraded",
        generation=artifact.shadowReviewGeneration,
        sourceObservation=artifact.sourceObservation,
        sourceTodayGeneration=artifact.sourceTodayGeneration,
        generatedAt=artifact.generatedAt,
        latestCaptureAt=artifact.latestCaptureAt,
        items=cards,
        categoryCounts=dict(Counter(card.category for card in cards)),
        primaryReasonCounts=dict(Counter(card.primaryReason for card in cards)),
        coverageLabelZh="这是从已就绪画像中冻结的 16 项本地体验样本，不是全部候选的最终精选，也不是 GitHub 全站排名。",
        candidateCount=artifact.fullCandidateUniverseCount,
        selectedCount=artifact.semanticDecisionCounts["SELECT_NOW"],
        publishedCount=len(cards),
        suppressedCount=sum(a.publicationDisposition.startswith("suppress_") for a in artifact.assessments),
        provenance={
            "pageReads": "immutable_shadow_serving",
            "sourceFreezeDigest": artifact.sourceFreezeDigest,
            "cohortManifestDigest": artifact.cohortManifestDigest,
            "productionEligible": False,
        },
        code="rardar_selection_local_shadow_review",
        currentGeneration=None,
        latestAttemptGeneration=artifact.shadowReviewGeneration,
        recallCount=artifact.fullRecallCount,
        profileReadyCount=artifact.healthyProfileCount,
        profileCoverage=round(artifact.healthyProfileCount / artifact.fullRecallCount, 6),
        assessmentCoverage=artifact.cohortAssessed / artifact.fullRecallCount,
        systemicFailure=artifact.audit["systemicProviderFailure"],
        safeFailureCodes=list(artifact.audit["failureHistogram"]),
        productionReady=False,
        reviewable=artifact.reviewable,
        shadowReviewState=artifact.shadowReviewState,
        shadowReviewGeneration=artifact.shadowReviewGeneration,
        candidateUniverseCount=artifact.fullCandidateUniverseCount,
        healthyProfileCount=artifact.healthyProfileCount,
        unresolvedProfileCount=artifact.unresolvedProfileCount,
        cohortSize=16,
        cohortAssessed=artifact.cohortAssessed,
        previewCount=len(cards),
        providerBudget=artifact.providerBudget,
    )


def _load(
    root: Path, generation: str | None = None, *, audit_raw: bool = False
) -> tuple[SelectionApiResponse, dict[int, SelectionProjectContext], str]:
    safe = _SafeRoot(str(root))
    safe.ensure_available()
    if generation is None:
        pointer_raw = safe.read_stable(f"{STORE}/current.json", maximum_bytes=4096)
        pointer = _strict_json(pointer_raw)
        if (
            set(pointer) != {"schemaVersion", "mode", "generation", "manifestSha256"}
            or pointer["schemaVersion"] != 1
            or pointer["mode"] != "local_shadow_review"
        ):
            raise ValueError("invalid shadow pointer")
        generation = pointer["generation"]
    else:
        pointer = None
    if not isinstance(generation, str) or not _GENERATION.fullmatch(generation):
        raise ValueError("invalid shadow generation")
    prefix = f"{STORE}/generations/{generation}/"
    manifest_raw = safe.read_stable(prefix + "manifest.json", maximum_bytes=16_384)
    if pointer is not None and _sha(manifest_raw) != pointer["manifestSha256"]:
        raise ValueError("shadow manifest hash mismatch")
    manifest = _strict_json(manifest_raw)
    if (
        set(manifest) != {"schemaVersion", "mode", "generation", "state", "files"}
        or manifest["schemaVersion"] != 1
        or manifest["mode"] != "local_shadow_review"
        or manifest["generation"] != generation
        or manifest["state"] != "ready"
    ):
        raise ValueError("invalid shadow manifest")
    files = manifest["files"]
    if (
        not isinstance(files, dict)
        or not 2 <= len(files) <= 8
        or not {"shadow-review.json", "serving.json"} <= files.keys()
    ):
        raise ValueError("invalid shadow inventory")
    loaded = {}
    for name, claimed in files.items():
        if name not in {"shadow-review.json", "serving.json"} and not re.fullmatch(r"projects/[1-9][0-9]*\.json", name):
            raise ValueError("invalid shadow path")
        if not isinstance(claimed, str) or not re.fullmatch(r"[a-f0-9]{64}", claimed):
            raise ValueError("invalid shadow hash")
        # Publication audits the full artifact. Request-time reads authenticate
        # only the bounded static projection, not all 16 raw assessments.
        if name == "shadow-review.json" and not audit_raw:
            plain(safe.path(prefix + name))
            continue
        raw = safe.read_stable(prefix + name, maximum_bytes=4 * 1024 * 1024)
        if _sha(raw) != claimed:
            raise ValueError("shadow artifact hash mismatch")
        loaded[name] = raw
    directory = root / STORE / "generations" / generation
    expected_top = {"manifest.json", "shadow-review.json", "serving.json"}
    project_files = {name.split("/")[1] for name in files if name.startswith("projects/")}
    if project_files:
        expected_top.add("projects")
    if {path.name for path in directory.iterdir()} != expected_top:
        raise ValueError("shadow disk inventory mismatch")
    if project_files:
        plain(directory / "projects")
        if {path.name for path in (directory / "projects").iterdir()} != project_files:
            raise ValueError("shadow project disk inventory mismatch")
    # No facts/profile rebuild, DB reads, provider calls or cache traversal on GET.
    snapshot = SelectionApiResponse.model_validate_json(loaded["serving.json"], strict=True)
    if snapshot.generation != generation:
        raise ValueError("shadow serving identity mismatch")
    contexts = {
        int(name[9:-5]): SelectionProjectContext.model_validate_json(raw, strict=True)
        for name, raw in loaded.items()
        if name.startswith("projects/")
    }
    cards = {card.githubRepositoryId: card for card in snapshot.items}
    if contexts.keys() != cards.keys():
        raise ValueError("shadow detail inventory mismatch")
    for identifier, context in contexts.items():
        if (
            context.selectionGenerationId != generation
            or context.sourceObservationSetId != snapshot.sourceObservation
            or context.card != cards[identifier]
        ):
            raise ValueError("shadow detail binding mismatch")
    if audit_raw:
        artifact = ShadowReviewArtifact.model_validate_json(loaded["shadow-review.json"], strict=True)
        if projection(artifact) != snapshot or {c.card.githubRepositoryId: c for c in artifact.contexts} != contexts:
            raise ValueError("shadow raw/projection mismatch")
    return snapshot, contexts, _sha(manifest_raw)


def load_shadow(root: Path, generation: str | None = None):
    try:
        return _load(root, generation)
    except (ValueError, OSError, KeyError, TypeError, ProviderBudgetError) as exc:
        raise RardarArtifactError("rardar_shadow_invalid", "Local Shadow integrity verification failed") from exc


def install_shadow(root: Path, artifact: ShadowReviewArtifact) -> bool:
    artifact = ShadowReviewArtifact.model_validate_json(artifact.model_dump_json(), strict=True)
    plain(root)
    store = root / STORE
    plain(store, missing=True)
    store.mkdir(exist_ok=True)
    generations = store / "generations"
    plain(generations, missing=True)
    generations.mkdir(exist_ok=True)
    generation = artifact.shadowReviewGeneration
    files = {
        "shadow-review.json": canonical(artifact.model_dump(mode="json")),
        "serving.json": canonical(projection(artifact).model_dump(mode="json")),
    }
    for context in artifact.contexts:
        files[f"projects/{context.card.githubRepositoryId}.json"] = canonical(context.model_dump(mode="json"))
    manifest = {
        "schemaVersion": 1,
        "mode": "local_shadow_review",
        "generation": generation,
        "state": "ready",
        "files": {name: _sha(raw) for name, raw in sorted(files.items())},
    }
    files["manifest.json"] = canonical(manifest)
    pointer = {
        "schemaVersion": 1,
        "mode": "local_shadow_review",
        "generation": generation,
        "manifestSha256": _sha(files["manifest.json"]),
    }
    with file_lock(store / "publish.lock"):
        target = generations / generation
        plain(target, missing=True)
        if not target.exists():
            with tempfile.TemporaryDirectory(prefix=".shadow-", dir=generations) as temporary:
                stage = Path(temporary) / generation
                stage.mkdir()
                for name, raw in files.items():
                    path = stage / name
                    path.parent.mkdir(exist_ok=True)
                    with path.open("xb") as handle:
                        handle.write(raw)
                        handle.flush()
                        os.fsync(handle.fileno())
                os.rename(stage, target)
        else:
            safe = _SafeRoot(str(target))
            if any(safe.read_stable(name, maximum_bytes=4 * 1024 * 1024) != raw for name, raw in files.items()):
                raise ValueError("immutable shadow generation conflict")
        _load(root, generation, audit_raw=True)  # Full audit before atomic publication.
        path = store / "current.json"
        plain(path, missing=True)
        if path.exists() and path.read_bytes() == canonical(pointer):
            return False
        atomic(path, pointer)
        return True


def rollback_shadow(root: Path, generation: str) -> None:
    store = root / STORE
    plain(store)
    with file_lock(store / "publish.lock"):
        _snapshot, _contexts, manifest_digest = _load(root, generation, audit_raw=True)
        atomic(
            store / "current.json",
            {
                "schemaVersion": 1,
                "mode": "local_shadow_review",
                "generation": generation,
                "manifestSha256": manifest_digest,
            },
        )
