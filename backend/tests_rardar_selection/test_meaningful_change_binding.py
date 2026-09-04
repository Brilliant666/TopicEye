from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.integrations.rardar import shadow_change_resume as resume_module, shadow_review as runner
from app.integrations.rardar.meaningful_change import (
    MeaningfulChangeContext,
    change_context,
    change_payload,
    validate_change_result,
    validate_context,
)
from app.integrations.rardar.selection import _contract_versions, _timeliness, _Usage, negative_control_cases
from app.integrations.rardar.selection_schemas import MeaningfulChangeResult, SelectionEvidenceAlias
from app.integrations.rardar.shadow_change_resume import ARTIFACT_NAME, ResumeInputs
from app.services.llm.provider import _cache_scope
from app.services.llm.provider_budget import (
    ProviderBudgetError,
    ProviderBudgetLedger,
    atomic,
    digest,
    single_provider_attempt,
)
from app.services.rardar_llm_control import RardarLLMResult, RardarLLMScene
from tests_rardar_selection.test_selection import _candidate, _metadata
from tests_rardar_selection.test_shadow_review import ShadowDouble, prepare

ROUTE = "c" * 64


def evidence(candidate, alias="T01", kind="release", text="Adds a reusable adapter API."):
    return SelectionEvidenceAlias(
        evidenceId=alias,
        sourceType=kind,
        sourcePath="github.releases.latest",
        sourceRevision="release-1",
        excerpt=text,
        githubRepositoryId=candidate.githubRepositoryId,
    )


def result(**updates):
    return MeaningfulChangeResult.model_validate(
        {
            "meaningfulRelease": "yes",
            "meaningfulUpdate": "no",
            "confidence": "high",
            "evidenceIds": ["T01"],
            **updates,
        },
        strict=True,
    )


def test_explicit_context_request_cache_and_strict_replay(tmp_path):
    c = _candidate(tmp_path)
    ev = [evidence(c)]
    context = change_context(c, ev, ROUTE)
    payload = change_payload(c, ev, context)
    assert payload["assessmentKind"] == "meaningful_change"
    assert payload["allowedEvidenceAliases"] == ["T01"]
    assert "never E/P" in payload["task"]
    assert "sourceType=release" in payload["task"] and "sourceType=revision" in payload["task"]
    assert "Star" in payload["task"] and "Do not assess Value" in payload["task"]
    assert not {"valueVerdict", "scopeStatus", "decision", "totalStars"} & payload.keys()
    assert validate_change_result(result(), context, c, ev, ROUTE) is None
    for update in ({"assessmentKind": "scope_value"}, {"scene": "rardar_worth_seeing_gate"}):
        with pytest.raises(ValidationError):
            MeaningfulChangeContext.model_validate({**context.model_dump(), **update}, strict=True)
    missing = context.model_dump()
    del missing["assessmentKind"]
    with pytest.raises(ValidationError):
        MeaningfulChangeContext.model_validate(missing, strict=True)
    # A correct response is rejected under the wrong validator context, but
    # revalidates locally under its exact original context without any caller.
    other = change_context(c, [evidence(c, alias="T02")], ROUTE)
    with pytest.raises(ValueError, match="context_mismatch"):
        validate_change_result(result(), other, c, ev, ROUTE)
    assert validate_change_result(result(), context, c, ev, ROUTE) is None
    assert other.allowedEvidenceSetDigest != context.allowedEvidenceSetDigest
    assert other.cache_digest != context.cache_digest
    revised = change_context(c, [ev[0].model_copy(update={"sourceRevision": "release-2"})], ROUTE)
    assert revised.cache_digest != context.cache_digest
    assert _cache_scope("rardar", context.scene, cache_identity=context.cache_digest) != _cache_scope(
        "rardar", "rardar_worth_seeing_gate", cache_identity=context.cache_digest
    )


@pytest.mark.parametrize("alias", ["E01", "P01", "github:repo:release:123", "T99"])
def test_no_cross_assessment_or_unknown_response_alias(tmp_path, alias):
    c = _candidate(tmp_path)
    ev = [evidence(c)]
    if alias != "T99":
        with pytest.raises(ValidationError):
            result(evidenceIds=[alias])
    else:
        assert (
            validate_change_result(result(evidenceIds=[alias]), change_context(c, ev, ROUTE), c, ev, ROUTE)
            == "invalid_evidence_alias"
        )


def test_input_alias_repository_source_and_digest_are_not_fuzzy(tmp_path):
    c = _candidate(tmp_path)
    for ev in [
        [evidence(c, alias="E01")],
        [evidence(c, kind="readme")],
        [evidence(c).model_copy(update={"githubRepositoryId": c.githubRepositoryId + 1})],
    ]:
        with pytest.raises(ValueError, match="evidence_context_invalid"):
            change_context(c, ev, ROUTE)
    ev = [evidence(c)]
    context = change_context(c, ev, ROUTE)
    for field in ("evidencePackageDigest", "allowedEvidenceSetDigest", "modelRouteIdentity"):
        with pytest.raises(ValueError, match="context_mismatch"):
            validate_context(context.model_copy(update={field: "a" * 64}), c, ev, ROUTE)
    with pytest.raises(ValueError, match="context_mismatch"):
        validate_context(context, c.model_copy(update={"pushedAt": c.pushedAt + timedelta(seconds=1)}), ev, ROUTE)


# Six original request shapes were release/T01, with discarded response fields.
# These are regression counterexamples, NOT claimed recovered Provider responses.
@pytest.mark.parametrize("identifier", [488641606, 1134844685, 24195339, 275993885, 111103465, 203938031])
def test_original_six_release_fixtures_keep_exact_type_guard(tmp_path, identifier):
    c = _candidate(tmp_path, identifier)
    ev = [evidence(c)]
    context = change_context(c, ev, ROUTE)
    assert validate_change_result(result(meaningfulUpdate="yes"), context, c, ev, ROUTE) == "wrong_assessment_evidence"
    assert validate_change_result(result(evidenceIds=[]), context, c, ev, ROUTE) == "wrong_assessment_evidence"
    assert validate_change_result(result(), context, c, ev, ROUTE) is None
    assert validate_change_result(result(meaningfulRelease="uncertain", evidenceIds=[]), context, c, ev, ROUTE) is None


@pytest.mark.asyncio
async def test_no_evidence_and_ordinary_patch_never_call_provider(tmp_path):
    c = _candidate(tmp_path)

    async def forbidden(**_):
        pytest.fail("no change evidence must not call Provider")

    for ev in ([], [evidence(c, text="Patch: bump dependencies, fix typo, update docs.")]):
        timely, attempts, failure = await _timeliness(c, ev, _Usage(), forbidden, model_route_identity=ROUTE)
        assert timely.verdict == "none" and attempts == 0 and failure is None
    empty = change_context(c, [], ROUTE)
    assert validate_change_result(result(meaningfulRelease="no", evidenceIds=[]), empty, c, [], ROUTE) is None
    assert validate_change_result(result(evidenceIds=[]), empty, c, [], ROUTE) == "wrong_assessment_evidence"


@pytest.mark.asyncio
async def test_receipt_replay_is_local_and_does_not_increment_ledger(tmp_path):
    c = _candidate(tmp_path)
    ev = [evidence(c)]
    context = change_context(c, ev, ROUTE)
    ledger = ProviderBudgetLedger.initialize(tmp_path / "run" / "provider-budget.json", "fixture-run")
    receipts = runner.StageReceipts(tmp_path / "run", "b" * 64, SimpleNamespace(legacy=lambda _: None))
    calls = []

    async def caller(**kwargs):
        calls.append(kwargs)
        with ledger.execution("meaningful_change"):
            return RardarLLMResult(result().model_dump_json(), _metadata(kwargs["scene"]))

    structured = []

    async def operation():
        return await _timeliness(
            c,
            ev,
            _Usage(),
            caller,
            model_route_identity=ROUTE,
            context=context,
            format_retry=False,
            result_observer=structured.append,
        )

    first = await receipts.run(
        "timeliness-101", operation, runner.SelectionTimeliness, context=context, structured=structured
    )
    before = ledger.snapshot()

    async def forbidden():
        pytest.fail("completed receipt must replay without dispatch")

    replayed = []
    assert (
        await receipts.run(
            "timeliness-101", forbidden, runner.SelectionTimeliness, context=context, structured=replayed
        )
        == first
    )
    assert len(calls) == 1 and ledger.snapshot() == before and replayed == [result()]
    path = receipts.root / "timeliness-101.json"
    tampered = json.loads(path.read_bytes())
    del tampered["assessmentContext"]["assessmentKind"]
    tampered["digest"] = digest({k: v for k, v in tampered.items() if k != "digest"})
    atomic(path, tampered)
    with pytest.raises(ValidationError):
        await receipts.run("timeliness-101", forbidden, runner.SelectionTimeliness, context=context)
    assert ledger.snapshot() == before


def test_single_dispatch_scope_blocks_transport_failover_and_nesting(tmp_path):
    ledger = ProviderBudgetLedger.initialize(tmp_path / "run" / "provider-budget.json", "fixture-run")
    with single_provider_attempt():
        with ledger.execution("meaningful_change"):
            pass
        with (
            pytest.raises(ProviderBudgetError, match="provider_operation_attempt_limit"),
            ledger.execution("meaningful_change"),
        ):
            pytest.fail("second upstream dispatch forbidden")
        with pytest.raises(ProviderBudgetError, match="scope_nested"), single_provider_attempt():
            pass
    assert ledger.snapshot()["attempted"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_count", [0, 1, 4, 6])
async def test_resume_only_six_changes_preserves_origin_and_budget(tmp_path, monkeypatch, bad_count):
    mirror, run, ledger, _double, origin, pool = await prepare(tmp_path, monkeypatch)
    # Model fixture calls above are not upstream calls. Seed a synthetic journal
    # representing the exact existing 28-attempt authorization, not a new real run.
    for stage, count in (("negative_control", 6), ("scope_value", 16), ("meaningful_change", 6)):
        for _ in range(count):
            with ledger.execution(stage):
                pass
    origin = origin.model_copy(update={"providerBudget": ledger.snapshot()})
    payload = origin.model_dump(mode="json")
    payload["digest"] = digest({k: v for k, v in payload.items() if k != "digest"})
    origin = runner.ShadowReviewArtifact.model_validate_json(json.dumps(payload), strict=True)
    atomic(run / "shadow-review-artifact.json", origin.model_dump(mode="json"))
    origin_raw = (run / "shadow-review-artifact.json").read_bytes()
    old_binding = json.loads((run / "shadow-run-binding.json").read_bytes())["binding"]
    updated = []
    contexts = {}
    for index, row in enumerate(pool):
        if index < 6:
            c = row.candidate.model_copy(update={"createdAt": row.candidate.lastObservedAt - timedelta(days=300)})
            row = replace(row, candidate=c, releases=(evidence(c),))
            contexts[c.githubRepositoryId] = change_context(c, list(row.releases), ROUTE)
        updated.append(row)
    freeze = {
        "digest": "a" * 64,
        "fullCandidateUniverseCount": 478,
        "fullRecallCount": 48,
        "unresolvedProfiles": origin.unresolvedProfiles,
    }
    cohort = {
        "digest": "b" * 64,
        "items": [
            {"githubRepositoryId": r.candidate.githubRepositoryId, "meaningfulChangeCandidate": i < 6}
            for i, r in enumerate(updated)
        ],
    }
    # Origin revalidation is tested separately; this unit isolates orchestration.
    source = SimpleNamespace(
        source_observation_set_id=origin.sourceObservation,
        today_generation_id=origin.sourceTodayGeneration,
        latest_capture_at=origin.latestCaptureAt.isoformat(),
    )
    inputs = ResumeInputs(freeze, cohort, source, [], updated, origin, old_binding, contexts, run)
    monkeypatch.setattr(runner, "load_resume_inputs", lambda *_: inputs)
    monkeypatch.setattr(runner, "freeze", lambda *_: pytest.fail("resume must not freeze"))
    calls = []

    class Caller(ShadowDouble):
        async def __call__(self, **kwargs):
            scene = kwargs["scene"]
            assert scene in {RardarLLMScene.WORTH_SEEING_MEANINGFUL_CHANGE, RardarLLMScene.WORTH_SEEING_COPY}
            calls.append(scene)
            stage = "meaningful_change" if scene == RardarLLMScene.WORTH_SEEING_MEANINGFUL_CHANGE else "user_copy"
            with ledger.execution(stage):
                if stage == "meaningful_change":
                    index = len([s for s in calls if s == scene])
                    value = result(meaningfulUpdate="yes" if index <= bad_count else "no")
                    return RardarLLMResult(value.model_dump_json(), _metadata(scene))
                # Deliberately invalid copy; one attempt, deterministic missing-copy fallback.
                return RardarLLMResult("not-json", _metadata(scene))

    artifact = await runner.resume_meaningful_change(mirror, run, ledger, route_identity=ROUTE, caller=Caller())
    assert artifact.cohortAssessed == 16 and artifact.negativeControlCount == 6
    assert calls.count(RardarLLMScene.WORTH_SEEING_MEANINGFUL_CHANGE) == 6
    assert calls.count(RardarLLMScene.WORTH_SEEING_COPY) == artifact.previewCount
    assert artifact.providerBudget["attempted"] == 34 + artifact.previewCount <= 40
    assert artifact.audit["rejectedMeaningfulResponses"] == bad_count
    assert artifact.audit["evidenceViolations"] == 0
    assert artifact.reviewable == (bad_count < 4)
    if bad_count >= 4:
        assert artifact.audit["blocker"] == "BLOCKED_MEANINGFUL_CHANGE_EVIDENCE_BINDING"
        assert artifact.previewCount == 0
    assert (run / "shadow-review-artifact.json").read_bytes() == origin_raw
    assert (run / ARTIFACT_NAME).is_file()
    prior = ledger.snapshot()
    repeated = await runner.resume_meaningful_change(mirror, run, ledger, route_identity=ROUTE, caller=Caller())
    assert repeated == artifact and ledger.snapshot() == prior
    for alteration in ("kind", "alias", "cache", "resume_version"):
        payload = artifact.model_dump(mode="json")
        first = next(iter(payload["audit"]["meaningfulChangeOutcomes"].values()))
        if alteration == "kind":
            del first["context"]["assessmentKind"]
        elif alteration == "alias":
            first["result"]["evidenceIds"] = ["E01"]
        elif alteration == "cache":
            payload["policyVersions"]["assessmentCacheDigest"] = "0" * 64
        else:
            del payload["policyVersions"]["meaningfulChangeResume"]
        payload["digest"] = digest({k: v for k, v in payload.items() if k != "digest"})
        with pytest.raises(ValidationError):
            runner.ShadowReviewArtifact.model_validate_json(json.dumps(payload), strict=True)
    assert ledger.snapshot() == prior


async def loader_fixture(tmp_path, monkeypatch):
    mirror, run, ledger, _, original, pool = await prepare(tmp_path, monkeypatch, weak=True)
    for stage, count in (("negative_control", 6), ("scope_value", 16), ("meaningful_change", 6)):
        for _ in range(count):
            with ledger.execution(stage):
                pass
    updated = [replace(r, releases=(evidence(r.candidate),) if i < 6 else ()) for i, r in enumerate(pool)]
    inventory = []
    import hashlib

    for row in updated:
        path = mirror / row.relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic profile")
        inventory.append({"path": row.relative_path, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    source = SimpleNamespace(
        source_observation_set_id=original.sourceObservation,
        today_generation_id=original.sourceTodayGeneration,
        today_published_set_digest="d" * 64,
    )
    recalled = [r.candidate for r in updated] * 3
    freeze = {
        "sourceObservation": source.source_observation_set_id,
        "sourceTodayGeneration": source.today_generation_id,
        "todayTop20Digest": source.today_published_set_digest,
        "sourceCaptureDigests": {"capture": "e" * 64},
        "profileInventory": inventory,
        "negativeControlsDigest": digest(negative_control_cases()),
        "recallSetDigest": digest([r.model_dump(mode="json") for r in recalled]),
        "fullCandidateUniverseCount": len(recalled),
        "healthyProfileSetDigest": digest(
            [
                {"path": r.relative_path, "sha256": r.file_digest, "profileRevision": r.collected.profile_revision}
                for r in updated
            ]
        ),
    }
    freeze["digest"] = digest(freeze)
    cohort = {
        "sourceFreezeDigest": freeze["digest"],
        "selectionPolicyVersion": {**_contract_versions(), "timelinessPrompt": "rardar-worth-seeing-change-v3"},
        "items": [
            {
                "githubRepositoryId": r.candidate.githubRepositoryId,
                "profileFileSha256": r.file_digest,
                "profileRevision": r.collected.profile_revision,
                "releaseEvidenceDigest": digest([e.model_dump(mode="json") for e in r.releases]),
                "meaningfulChangeCandidate": i < 6,
            }
            for i, r in enumerate(updated)
        ],
    }
    cohort["digest"] = digest(cohort)
    payload = original.model_dump(mode="json")
    payload.update(
        sourceFreezeDigest=freeze["digest"],
        cohortManifestDigest=cohort["digest"],
        providerBudget=ledger.snapshot(),
        reviewable=False,
        shadowReviewState="incomplete",
    )
    payload["audit"]["evidenceViolations"] = 6
    payload["policyVersions"]["timelinessPrompt"] = "rardar-worth-seeing-change-v3"
    for i, assessment in enumerate(payload["assessments"]):
        if i < 6:
            assessment.update(
                timelinessEvidence=[e.model_dump(mode="json") for e in updated[i].releases],
                timeliness=runner.neutral_timeliness().model_dump(mode="json"),
                failureCode="wrong_assessment_evidence",
            )
    payload["digest"] = digest({k: v for k, v in payload.items() if k != "digest"})
    origin = runner.ShadowReviewArtifact.model_validate_json(json.dumps(payload), strict=True)
    binding = digest(
        {
            "source": freeze["digest"],
            "cohort": cohort["digest"],
            "route": ROUTE,
            "policy": origin.policyVersions,
            "runId": ledger.run_id,
        }
    )
    for i, row in enumerate(origin.assessments):
        if i < 6:
            p = run / "stage-receipts" / f"timeliness-{row.candidate.githubRepositoryId}.json"
            receipt = json.loads(p.read_bytes())
            receipt.update(value=row.timeliness.model_dump(mode="json"), failure="wrong_assessment_evidence")
            atomic(p, receipt)
    for p in (run / "stage-receipts").glob("*.json"):
        receipt = json.loads(p.read_bytes())
        receipt["binding"] = binding
        receipt["digest"] = digest({k: v for k, v in receipt.items() if k != "digest"})
        atomic(p, receipt)
    atomic(run / "shadow-source-freeze-manifest.json", freeze)
    atomic(run / "shadow-review-cohort-manifest.json", cohort)
    atomic(run / "shadow-run-binding.json", {"binding": binding})
    atomic(run / "shadow-review-artifact.json", origin.model_dump(mode="json"))
    monkeypatch.setattr(resume_module, "healthy_pool", lambda *_: (source, recalled, updated))
    monkeypatch.setattr(resume_module, "build_candidate_universe", lambda *_: (recalled, None))
    monkeypatch.setattr(resume_module, "_source_identities", lambda *_: {"sourceCaptureDigests": {"capture": "e" * 64}})
    return mirror, run, ledger, source


@pytest.mark.asyncio
@pytest.mark.parametrize("drift", [None, "route", "source", "profile", "late_receipt", "ledger", "cohort"])
async def test_full_readonly_origin_preflight_rejects_drift_without_dispatch(tmp_path, monkeypatch, drift):
    mirror, run, ledger, source = await loader_fixture(tmp_path, monkeypatch)
    before = ledger.snapshot()
    if drift == "source":
        source.today_generation_id = "another-generation"
    elif drift == "profile":
        (mirror / "profiles/100.json").write_bytes(b"changed")
    elif drift == "late_receipt":
        (run / "stage-receipts/timeliness-115.json").write_bytes(b"{}")
    elif drift in {"ledger", "cohort"}:
        path = run / "shadow-review-artifact.json"
        payload = json.loads(path.read_bytes())
        if drift == "ledger":
            budget = payload["providerBudget"]
            budget["journalDigest"] = "0" * 64
            budget["digest"] = digest({k: v for k, v in budget.items() if k != "digest"})
        else:
            payload["cohortManifestDigest"] = "0" * 64
        payload["digest"] = digest({k: v for k, v in payload.items() if k != "digest"})
        atomic(path, payload)
    if drift:
        with pytest.raises(runner.ShadowIntegrityError):
            resume_module.load_resume_inputs(mirror, run, ledger, "a" * 64 if drift == "route" else ROUTE)
    else:
        loaded = resume_module.load_resume_inputs(mirror, run, ledger, ROUTE)
        assert len(loaded.change_contexts) == 6
    assert ledger.snapshot() == before
