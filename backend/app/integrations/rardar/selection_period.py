"""One immutable publication over validated batches of one facts/policy period.

Batch artifacts remain schema 1 and keep their original validation contracts.
The schema 2 envelope is an index of exact immutable children, not a synthetic
batch claiming that unprocessed repositories were assessed.
"""

from __future__ import annotations

import os
from collections import Counter
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError

from app.integrations.rardar.selection import _pack
from app.integrations.rardar.selection_schemas import (
    SelectionServingFile,
    SelectionServingManifest,
    SelectionServingPointer,
    SelectionServingSnapshot,
)
from app.integrations.rardar.selection_serving import (
    BuiltSelectionServing,
    SelectionServingError,
    SelectionServingLoader,
    _canonical_bytes,
    _sha,
    install_selection_serving,
)

_BOUND = (
    "sourceObservationSetId",
    "sourceManifestSha256",
    "sourceInventorySha256",
    "sourceCaptureInventoryDigest",
    "todayGenerationId",
    "todayExplosionSha256",
    "todayPublishedSetDigest",
    "candidateUniverseDigest",
    "modelRouteIdentity",
    "contractVersions",
)


class Child(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    generation: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{1,190}$")
    manifestSha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class PeriodEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schemaVersion: Literal[2] = 2
    policyVersion: Literal["worth-seeing-period-v1"] = "worth-seeing-period-v1"
    selectionGenerationId: str
    sourceObservationSetId: str
    generatedAt: AwareDatetime
    periodKey: str = Field(pattern=r"^[a-f0-9]{64}$")
    children: list[Child] = Field(min_length=1, max_length=500)
    payloadDigest: str = Field(pattern=r"^[a-f0-9]{64}$")


class PeriodView:
    """Validated internal projection; never serialized as a legacy artifact."""

    def __init__(self, first, **values):
        self._first = first
        self.__dict__.update(values)

    def __getattr__(self, name):
        return getattr(self._first, name)


def _project(loader, children):
    artifacts = []
    contexts = {}
    all_rows = {}
    for child in children:
        manifest, _ = loader._manifest(child.generation, child.manifestSha256)
        raw = loader._file(child.generation, next(x for x in manifest.files if x.path == "raw/selection.json"))
        from app.services.llm.strict_json import loads_strict_json

        if loads_strict_json(raw).get("schemaVersion") != 1:
            raise SelectionServingError("rardar_selection_invalid", "Period children must be original batches")
        artifact = loader.validate_generation(child.generation)
        if len(artifact.assessments) != 1 or artifact.processedCount != 1:
            raise SelectionServingError(
                "rardar_selection_period_requires_singleton", "Period children must contain one project before packing"
            )
        if artifacts and any(getattr(artifact, name) != getattr(artifacts[0], name) for name in _BOUND):
            raise SelectionServingError("rardar_selection_period_mixed", "Period source or policy differs")
        artifacts.append(artifact)
        for row in artifact.assessments:
            identifier = row.candidate.githubRepositoryId
            if identifier in all_rows:
                raise SelectionServingError("rardar_selection_period_overlap", "Period batches overlap")
            all_rows[identifier] = row
        for identifier in manifest.projectIds:
            context, _ = loader.load_project_with_etag(identifier, child.generation)
            contexts[identifier] = context
    first = artifacts[0]
    period_key = _sha(_canonical_bytes({name: getattr(first, name) for name in _BOUND}))
    # Only already validated, publishable child contexts can enter packing.
    eligible = [
        all_rows[key].model_copy(update={"displayOrder": None})
        for key in sorted(contexts)
        if all_rows[key].value_is_publishable() and all_rows[key].copyResult is not None
    ]
    packed = _pack(eligible)
    packed_by_id = {item.candidate.githubRepositoryId: item for item in packed}
    chosen = sorted((x for x in packed if x.publicationDisposition == "publish"), key=lambda x: x.displayOrder)
    chosen_ids = {x.candidate.githubRepositoryId for x in chosen}
    rows = [
        row.model_copy(
            update={
                "publicationDisposition": "publish"
                if key in chosen_ids
                else (packed_by_id[key].publicationDisposition if key in packed_by_id else row.publicationDisposition),
                "displayOrder": next((x.displayOrder for x in chosen if x.candidate.githubRepositoryId == key), None),
                "copyResult": row.copyResult if key in chosen_ids else None,
                "nearDuplicateGroup": packed_by_id[key].nearDuplicateGroup
                if key in packed_by_id
                else row.nearDuplicateGroup,
            }
        )
        for key, row in sorted(all_rows.items())
    ]
    rows = [type(row).model_validate_json(_canonical_bytes(row)) for row in rows]
    profile_ready = sum(x.profileReadyCount or 0 for x in artifacts)
    retryable = sum(x.profileRetryableFailureCount or 0 for x in artifacts)
    permanent = sum(x.profilePermanentUnavailableCount or 0 for x in artifacts)
    failure = dict(sum((Counter(x.failureSummary) for x in artifacts), Counter()))
    gate_count = sum(x.gate is not None for x in rows)
    resolved = sum(x.semanticResolvedCount or 0 for x in artifacts)
    assessment_denominator = (
        len(rows)
        if first.contractVersions.get("profileEvidencePolicy") == "validated-raw-value-evidence-v3"
        else profile_ready
    )
    # A bounded evaluated set may legitimately contain no publishable project.
    # Coverage reports unprocessed scope; it is not an all-universe gate.
    fully_resolved = (
        bool(rows)
        and resolved == len(rows)
        and not failure
        and not any(item.negativeControlFailures for item in artifacts)
    )
    state = "ready" if chosen else "empty" if fully_resolved else "degraded"
    digest = _sha(_canonical_bytes({"period": period_key, "children": children}))
    generation = f"period-{digest[:32]}"
    view = PeriodView(
        first,
        schemaVersion=2,
        selectionGenerationId=generation,
        generatedAt=max(x.generatedAt for x in artifacts),
        periodKey=period_key,
        inputDigest=digest,
        payloadDigest=digest,
        executionMode="period",
        assessments=rows,
        recalledCount=len(rows),
        assessedCount=len(rows),
        processedCount=len(rows),
        processedCandidateIds=sorted(all_rows),
        unprocessedCandidateIds=[],
        publishedCount=len(chosen),
        state=state,
        currentEligible=state in {"ready", "empty"},
        latestAttemptGeneration=generation,
        profileReadyCount=profile_ready,
        profileRetryableFailureCount=retryable,
        profilePermanentUnavailableCount=permanent,
        profileReboundCount=sum(x.profileReboundCount or 0 for x in artifacts),
        profileRebuiltCount=sum(x.profileRebuiltCount or 0 for x in artifacts),
        gateAssessedCount=gate_count,
        semanticResolvedCount=resolved,
        unresolvedCount=len(rows) - resolved,
        failureSummary=failure,
        failureHistogram=failure,
        decisionCounts=dict(Counter(x.semanticDecision for x in rows)),
        publicationCounts=dict(Counter(x.publicationDisposition for x in rows)),
        usage=SimpleNamespace(
            **{
                name: None
                if any(getattr(x.usage, name) is None for x in artifacts)
                else sum(getattr(x.usage, name) for x in artifacts)
                for name in type(artifacts[0].usage).model_fields
            }
        ),
        systemicFailureCodes=[],
        profileCoverage=round(profile_ready / len(rows), 6) if rows else 1.0,
        assessmentCoverage=round(gate_count / assessment_denominator, 6) if assessment_denominator else 0.0,
        profileFailureSummary=dict(sum((Counter(x.profileFailureSummary or {}) for x in artifacts), Counter())),
    )
    return view, [contexts[x.candidate.githubRepositoryId] for x in chosen]


def load_period_view(loader, raw):
    try:
        envelope = PeriodEnvelope.model_validate_json(raw)
    except ValidationError as exc:
        raise SelectionServingError("rardar_selection_invalid", "Period envelope is invalid") from exc
    unsigned = envelope.model_dump(mode="json", exclude={"payloadDigest"})
    if _sha(_canonical_bytes(unsigned)) != envelope.payloadDigest:
        raise SelectionServingError("rardar_selection_invalid", "Period payload digest differs")
    if len({x.generation for x in envelope.children}) != len(envelope.children):
        raise SelectionServingError("rardar_selection_invalid", "Duplicate period child")
    if envelope.children != sorted(envelope.children, key=lambda x: x.generation):
        raise SelectionServingError("rardar_selection_invalid", "Period inventory is not canonical")
    view, _ = _project(loader, envelope.children)
    if any(
        getattr(view, key) != getattr(envelope, key)
        for key in (
            "selectionGenerationId",
            "sourceObservationSetId",
            "generatedAt",
            "periodKey",
        )
    ):
        raise SelectionServingError("rardar_selection_invalid", "Period projection differs")
    return view


def build_period_serving(target: Path, generations: list[str]) -> BuiltSelectionServing:
    if not generations:
        raise SelectionServingError("rardar_selection_invalid", "Period has no completed children")
    loader = SelectionServingLoader(target)
    children = [
        Child(generation=key, manifestSha256=_sha(loader._manifest(key)[1])) for key in sorted(set(generations))
    ]
    view, contexts = _project(loader, children)
    payload = {
        "schemaVersion": 2,
        "policyVersion": "worth-seeing-period-v1",
        "selectionGenerationId": view.selectionGenerationId,
        "sourceObservationSetId": view.sourceObservationSetId,
        "generatedAt": view.generatedAt,
        "periodKey": view.periodKey,
        "children": children,
    }
    envelope = PeriodEnvelope(**payload, payloadDigest=_sha(_canonical_bytes(payload)))
    cards = [x.card for x in contexts]
    snapshot = SelectionServingSnapshot(
        schemaVersion=2,
        selectionGenerationId=view.selectionGenerationId,
        sourceObservationSetId=view.sourceObservationSetId,
        generatedAt=view.generatedAt,
        latestCaptureId=view.latestCaptureId,
        latestCaptureAt=view.latestCaptureAt,
        sourceWindowStart=view.sourceWindowStart,
        sourceWindowEnd=view.sourceWindowEnd,
        status=view.state,
        items=cards,
        categoryCounts=dict(Counter(x.category for x in cards)),
        primaryReasonCounts=dict(Counter(x.primaryReason for x in cards)),
        coverageLabelZh=f"本期已处理 {view.processedCount} / {view.universeCount} 个候选，未处理不代表淘汰。",
        sourceCoverageState=view.sourceCoverageState,
        sourceTodayGeneration=view.todayGenerationId,
        candidateCount=view.universeCount,
        recallCount=view.universeCount,
        executionMode="period",
        processedCount=view.processedCount,
        unprocessedCount=view.universeCount - view.processedCount,
        selectedCount=sum(x.value_is_publishable() for x in view.assessments),
        publishedCount=len(cards),
        suppressedCount=sum(x.value_is_publishable() for x in view.assessments) - len(cards),
        currentGeneration=view.selectionGenerationId if view.currentEligible else None,
        latestAttemptGeneration=view.selectionGenerationId,
        profileReadyCount=view.profileReadyCount,
        profileReboundCount=view.profileReboundCount,
        profileRebuiltCount=view.profileRebuiltCount,
        retryableFailureCount=view.profileRetryableFailureCount,
        permanentFailureCount=view.profilePermanentUnavailableCount,
        profileCoverage=view.profileCoverage,
        assessmentCoverage=view.assessmentCoverage,
        safeFailureCodes=sorted(view.failureSummary)[:20],
    )
    files = {"raw/selection.json": _canonical_bytes(envelope), "serving/selection.json": _canonical_bytes(snapshot)}
    for context in contexts:
        projected = context.model_copy(
            update={"selectionGenerationId": view.selectionGenerationId, "generatedAt": view.generatedAt}
        )
        files[f"serving/projects/{context.card.githubRepositoryId}.json"] = _canonical_bytes(projected)
    manifest = SelectionServingManifest(
        schemaVersion=1,
        state="ready",
        selectionGenerationId=view.selectionGenerationId,
        sourceObservationSetId=view.sourceObservationSetId,
        rawArtifactSha256=_sha(files["raw/selection.json"]),
        generatedAt=view.generatedAt,
        files=[SelectionServingFile(path=p, sha256=_sha(b), bytes=len(b)) for p, b in sorted(files.items())],
        projectIds=[x.githubRepositoryId for x in cards],
    )
    files["manifest.json"] = _canonical_bytes(manifest)
    pointer = SelectionServingPointer(
        schemaVersion=1,
        selectionGenerationId=view.selectionGenerationId,
        sourceObservationSetId=view.sourceObservationSetId,
        manifestSha256=_sha(files["manifest.json"]),
        activatedAt=view.generatedAt,
        activationState=view.state,
        activationPolicyVersion="worth-seeing-activation-v2",
    )
    return BuiltSelectionServing(
        view.selectionGenerationId,
        view.sourceObservationSetId,
        pointer.manifestSha256,
        _canonical_bytes(pointer),
        files,
        view.state,
        view.currentEligible,
    )


@contextmanager
def _publication_locks(target: Path):
    from app.integrations.rardar.selection_execution import selection_writer

    lock = target.parent / f".{target.name}.sync.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise SelectionServingError("rardar_selection_sync_running", "Fact sync owns the publication lock") from exc
    try:
        os.close(fd)
        with selection_writer(target):
            yield
    finally:
        lock.unlink(missing_ok=True)


def publish_period(
    target: Path,
    generations: list[str],
    *,
    expected_source_id: str,
    expected_today_generation: str,
    expected_route_identity: str | None = None,
):
    from app.integrations.rardar.selection_source import SelectionSourceAdapter
    from app.integrations.rardar.serving import ServingProjectionLoader

    with _publication_locks(target):
        source = SelectionSourceAdapter.from_config(str(target)).load()
        today, _ = ServingProjectionLoader(str(target)).load_today_with_etag()
        if today.generationId != expected_today_generation:
            raise SelectionServingError("rardar_selection_source_changed", "Published Today changed")
        if (
            source.source_observation_set_id != expected_source_id
            or source.today_generation_id != expected_today_generation
        ):
            raise SelectionServingError("rardar_selection_source_changed", "Period source is no longer current")
        # The caller may have planned before another same-period publication.
        generations = with_current_period(target, generations)
        built = build_period_serving(target, generations)
        view = load_period_view(SelectionServingLoader(target), built.files["raw/selection.json"])
        if view.sourceObservationSetId != expected_source_id or view.todayGenerationId != expected_today_generation:
            raise SelectionServingError("rardar_selection_source_changed", "Period binding is not current")
        if expected_route_identity is not None and view.modelRouteIdentity != expected_route_identity:
            raise SelectionServingError("rardar_selection_route_changed", "Period route is no longer current")
        try:
            current = SelectionServingLoader(target).validate_generation()
        except SelectionServingError as exc:
            if exc.code != "rardar_selection_not_configured":
                raise
        else:
            if current.sourceWindowEnd > view.sourceWindowEnd or (
                getattr(current, "periodKey", None) == view.periodKey
                and not set(current.processedCandidateIds).issubset(view.processedCandidateIds)
            ):
                raise SelectionServingError(
                    "rardar_selection_period_stale", "Late period cannot replace newer coverage"
                )
        loader = SelectionServingLoader(target)
        try:
            active_pointer, active_raw = loader._pointer()
        except SelectionServingError as exc:
            if exc.code != "rardar_selection_not_configured":
                raise
            active_pointer, active_raw = None, None
        if active_pointer is not None and active_pointer.selectionGenerationId == built.selection_generation_id:
            built = replace(built, pointer_raw=active_raw)
        else:
            pointer = SelectionServingPointer.model_validate_json(built.pointer_raw)
            built = replace(
                built, pointer_raw=_canonical_bytes(pointer.model_copy(update={"activatedAt": datetime.now(UTC)}))
            )
        return install_selection_serving(target, built)


def with_current_period(target: Path, generations: list[str]) -> list[str]:
    """Retain same-period work; a retried singleton replaces its prior record."""
    loader = SelectionServingLoader(target)
    incoming = [loader.validate_generation(key) for key in generations]
    if not incoming:
        return []
    identifiers = {row.candidate.githubRepositoryId for item in incoming for row in item.assessments}
    try:
        current = loader.validate_generation()
    except SelectionServingError as exc:
        if exc.code == "rardar_selection_not_configured":
            return generations
        raise
    if current.schemaVersion != 2 or any(getattr(current, key) != getattr(incoming[0], key) for key in _BOUND):
        return generations
    manifest, _ = loader._manifest(current.selectionGenerationId)
    envelope = PeriodEnvelope.model_validate_json(
        loader._file(current.selectionGenerationId, next(x for x in manifest.files if x.path == "raw/selection.json"))
    )
    retained = []
    replaced = set()
    for child in envelope.children:
        artifact = loader.validate_generation(child.generation)
        if not identifiers.intersection(row.candidate.githubRepositoryId for row in artifact.assessments):
            retained.append(child.generation)
        elif len(artifact.assessments) == 1:
            old = artifact.assessments[0]
            candidates = [
                item
                for item in incoming
                if len(item.assessments) == 1
                and item.assessments[0].candidate.githubRepositoryId == old.candidate.githubRepositoryId
            ]
            for item in candidates:
                new = item.assessments[0]
                old_complete = old.gate is not None and not old.failureCode
                new_complete = new.gate is not None and not new.failureCode
                same_facts = old.candidate == new.candidate
                if same_facts and (
                    (old_complete and not new_complete)
                    or (
                        old_complete == new_complete
                        and (artifact.generatedAt, artifact.selectionGenerationId)
                        > (item.generatedAt, item.selectionGenerationId)
                    )
                ):
                    retained.append(child.generation)
                    replaced.add(item.selectionGenerationId)
    return sorted(set(retained + [item for item in generations if item not in replaced]))
