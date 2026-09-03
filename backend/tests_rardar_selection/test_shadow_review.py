from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.integrations.rardar import shadow_review as runner, shadow_serving
from app.integrations.rardar.adapter import RardarArtifactError
from app.integrations.rardar.selection import _profile_project
from app.integrations.rardar.serving_profiles import build_official_profiles
from app.integrations.rardar.shadow_cohort import HealthyProfile, ShadowIntegrityError, choose_cohort
from app.integrations.rardar.shadow_schemas import ShadowReviewArtifact
from app.services.llm.provider_budget import ProviderBudgetLedger, digest
from app.services.rardar_intelligence import load_selection_snapshot
from app.services.rardar_llm_control import RardarLLMResult, RardarLLMScene
from tests_rardar_selection.test_selection import ModelDouble, _candidate, _client, _source


class ShadowDouble(ModelDouble):
    async def __call__(self, **kwargs):
        result = await super().__call__(**kwargs)
        if kwargs["scene"] == RardarLLMScene.WORTH_SEEING_COPY:
            value = json.loads(result.content)
            value["evidenceIds"] = ["E01"]
            result = RardarLLMResult(json.dumps(value), result.metadata)
        return result


async def prepare(tmp_path, monkeypatch, *, weak=False):
    mirror, source = _source(tmp_path)
    candidates = []
    for identifier in range(100, 132):
        candidate = _candidate(tmp_path, identifier)
        candidate = candidate.model_copy(
            update={
                "createdAt": candidate.lastObservedAt - timedelta(days=2 if identifier < 116 else 300),
                "observedStarDelta": identifier - 100,
                "totalStars": 1000,
                "recallChannels": ["reusable_asset", "momentum"],
            }
        )
        candidates.append(candidate)
    async with _client() as client:
        profiles = await build_official_profiles(
            [_profile_project(c, i) for i, c in enumerate(candidates, 1)],
            source.source_observation_set_id,
            mirror / "profile-cache",
            translate_top=0,
            concurrency=1,
            client=client,
            allow_model_generation=False,
        )
    pool = [
        HealthyProfile(
            c,
            profiles.profiles[c.githubRepositoryId],
            f"profiles/{c.githubRepositoryId}.json",
            "a" * 64,
            ("dev-tools", "ai-agent", "productivity", "data-infra", "video-content", "other")[i % 6],
            (),
        )
        for i, c in enumerate(candidates)
    ]
    # Execute a fixed 16 synthetic fixture cohort; selection itself is tested separately.
    pool = pool[:16]
    source_freeze = {
        "digest": "a" * 64,
        "fullCandidateUniverseCount": 478,
        "fullRecallCount": 48,
        "unresolvedProfiles": [{"githubRepositoryId": i, "repository": f"pending/{i}"} for i in range(16, 48)],
    }
    cohort = {
        "digest": "b" * 64,
        "items": [
            {"githubRepositoryId": row.candidate.githubRepositoryId, "meaningfulChangeCandidate": False} for row in pool
        ],
    }
    monkeypatch.setattr(runner, "freeze", lambda *args: (source_freeze, cohort))
    monkeypatch.setattr(runner, "healthy_pool", lambda *args: (source, candidates, pool))
    run = tmp_path / "run"
    ledger = ProviderBudgetLedger.initialize(run / "provider-budget.json", "fixture-run")
    double = ShadowDouble(regular_value="weak" if weak else "strong")
    artifact = await runner.build_shadow_review(mirror, run, ledger, route_identity="c" * 64, caller=double)
    return mirror, run, ledger, double, artifact, pool


@pytest.mark.asyncio
async def test_ready_preview_6_overall_degraded_static_idempotent(tmp_path, monkeypatch):
    mirror, run, ledger, double, artifact, _pool = await prepare(tmp_path, monkeypatch)
    assert artifact.state == "degraded" and artifact.productionEligible is False
    assert artifact.reviewable and artifact.shadowReviewState == "ready"
    assert artifact.cohortAssessed == 16 and artifact.previewCount == 6
    assert artifact.providerBudget["attempted"] == 0  # Mock calls consume no upstream budget.
    before_calls = len(double.calls)
    repeated = await runner.build_shadow_review(mirror, run, ledger, route_identity="c" * 64, caller=double)
    assert repeated == artifact and len(double.calls) == before_calls
    full = mirror / "discover-worth-seeing"
    full.mkdir(exist_ok=True)
    (full / "current.json").write_bytes(b"untouched full current")
    assert shadow_serving.install_shadow(mirror, artifact)
    assert not shadow_serving.install_shadow(mirror, artifact)
    snapshot, contexts, _etag = shadow_serving.load_shadow(mirror)
    assert snapshot.reviewable and len(contexts) == 6
    assert (full / "current.json").read_bytes() == b"untouched full current"
    for context in contexts.values():
        assert context.selectionGenerationId == artifact.shadowReviewGeneration
    local = SimpleNamespace(
        RARDAR_INTELLIGENCE_DATA_DIR=str(mirror), RARDAR_LOCAL_SHADOW_REVIEW=True, is_production=False
    )
    assert load_selection_snapshot(local)[0] == snapshot
    # Production ignores the opt-in and keeps its existing full Selection reader.
    sentinel = RuntimeError("full-selection-reader")
    monkeypatch.setattr(
        "app.services.rardar_intelligence.SelectionServingLoader.load_state_with_etag",
        lambda *_: (_ for _ in ()).throw(sentinel),
    )
    local.is_production = True
    with pytest.raises(RuntimeError, match="full-selection-reader"):
        load_selection_snapshot(local)


@pytest.mark.asyncio
async def test_request_reads_static_only_and_rollback_reaudits_raw(tmp_path, monkeypatch):
    mirror, _run, _ledger, _double, artifact, _pool = await prepare(tmp_path, monkeypatch)
    shadow_serving.install_shadow(mirror, artifact)
    original = shadow_serving._SafeRoot.read_stable
    reads = []

    def track(self, relative, **kwargs):
        reads.append(relative)
        assert not relative.endswith("shadow-review.json")
        return original(self, relative, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(shadow_serving._SafeRoot, "read_stable", track)
        assert shadow_serving.load_shadow(mirror)[0].previewCount == 6
    assert reads and not any("profile-cache" in path for path in reads)
    directory = mirror / shadow_serving.STORE / "generations" / artifact.shadowReviewGeneration
    (directory / "shadow-review.json").write_bytes(b"{}")
    pointer = mirror / shadow_serving.STORE / "current.json"
    before = pointer.read_bytes()
    with pytest.raises(ValueError, match="hash mismatch"):
        shadow_serving.rollback_shadow(mirror, artifact.shadowReviewGeneration)
    assert pointer.read_bytes() == before


@pytest.mark.asyncio
async def test_zero_select_is_reviewable_empty_no_refill(tmp_path, monkeypatch):
    _mirror, _run, _ledger, double, artifact, _pool = await prepare(tmp_path, monkeypatch, weak=True)
    assert artifact.reviewable and artifact.shadowReviewState == "empty"
    assert artifact.previewCount == 0 and artifact.cohortAssessed == 16
    assert not any(scene == RardarLLMScene.WORTH_SEEING_COPY for scene, _ in double.calls)


@pytest.mark.asyncio
async def test_tamper_fail_closed_and_pointer_interruption_preserves_previous(tmp_path, monkeypatch):
    mirror, _run, _ledger, _double, artifact, _pool = await prepare(tmp_path, monkeypatch)
    shadow_serving.install_shadow(mirror, artifact)
    pointer = mirror / shadow_serving.STORE / "current.json"
    original = pointer.read_bytes()
    generation = mirror / shadow_serving.STORE / "generations" / artifact.shadowReviewGeneration
    serving = generation / "serving.json"
    saved = serving.read_bytes()
    serving.write_bytes(b"{}")
    with pytest.raises(RardarArtifactError, match="integrity"):
        shadow_serving.load_shadow(mirror)
    assert pointer.read_bytes() == original
    serving.write_bytes(saved)
    monkeypatch.setattr(shadow_serving, "atomic", lambda *_: (_ for _ in ()).throw(OSError("interrupt")))
    with pytest.raises(OSError):
        shadow_serving.rollback_shadow(mirror, artifact.shadowReviewGeneration)
    assert pointer.read_bytes() == original
    with pytest.raises(RardarArtifactError):
        shadow_serving.load_shadow(mirror, "../escape")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change", ["budget", "coverage", "decision", "cross_repository", "production", "incomplete_ready"]
)
async def test_artifact_audit_rejects_contradictions(tmp_path, monkeypatch, change):
    _mirror, _run, _ledger, _double, artifact, _pool = await prepare(tmp_path, monkeypatch)
    payload = artifact.model_dump(mode="json")
    if change == "budget":
        payload["providerBudget"]["attempted"] = 41
    elif change == "coverage":
        payload["cohortAssessed"] = 15
    elif change == "decision":
        payload["semanticDecisionCounts"]["REJECT"] = 50
    elif change == "cross_repository":
        payload["assessments"][0]["valueEvidence"][0]["githubRepositoryId"] += 1
    elif change == "production":
        payload["productionEligible"] = True
    else:
        payload["shadowReviewState"] = "incomplete"
    payload["digest"] = digest({k: v for k, v in payload.items() if k != "digest"})
    with pytest.raises(ValidationError):
        ShadowReviewArtifact.model_validate_json(json.dumps(payload), strict=True)


@pytest.mark.asyncio
async def test_cohort_determinism_diversity_cap_and_insufficient_pool(tmp_path, monkeypatch):
    _mirror, _run, _ledger, _double, _artifact, pool = await prepare(tmp_path, monkeypatch)
    extra = []
    for index, row in enumerate(pool):
        candidate = row.candidate.model_copy(
            update={
                "githubRepositoryId": 1000 + index,
                "createdAt": row.candidate.lastObservedAt - timedelta(days=300),
                "observedStarDelta": 0,
            }
        )
        extra.append(replace(row, candidate=candidate))
    selected, _ = choose_cohort(pool + extra)
    assert selected == choose_cohort(list(reversed(pool + extra)))[0]
    assert len({row["githubRepositoryId"] for row in selected}) == 16
    assert len({row["category"] for row in selected}) >= 4
    assert sum(row["momentumBand"] == "top_quartile" for row in selected) <= 6
    assert sum(row["momentumOnly"] for row in selected) <= 4
    with pytest.raises(ShadowIntegrityError, match="insufficient"):
        choose_cohort(pool[:15])


@pytest.mark.asyncio
async def test_crash_stage_receipt_does_not_repeat_provider(tmp_path):
    root = tmp_path / "run"
    root.mkdir()
    receipts = runner.StageReceipts(root, "frozen-binding")

    async def interrupted():
        raise RuntimeError("process interrupted")

    with pytest.raises(RuntimeError):
        await receipts.run("gate-123", interrupted, runner.SelectionGateResult)

    async def forbidden():
        pytest.fail("a started receipt must not repeat an initial call")

    assert await receipts.run("gate-123", forbidden, runner.SelectionGateResult) == (None, 0, "process_interrupted")


@pytest.mark.asyncio
async def test_copy_failure_does_not_change_preview_membership(tmp_path, monkeypatch):
    class CopyFailure(ShadowDouble):
        async def __call__(self, **kwargs):
            result = await super().__call__(**kwargs)
            if kwargs["scene"] == RardarLLMScene.WORTH_SEEING_COPY:
                return RardarLLMResult("not-json", result.metadata)
            return result

    monkeypatch.setattr(__name__ + ".ShadowDouble", CopyFailure)
    _mirror, _run, _ledger, _double, artifact, _pool = await prepare(tmp_path, monkeypatch)
    assert artifact.reviewable and artifact.previewCount == 6
    assert artifact.semanticDecisionCounts["SELECT_NOW"] == 16
    assert all(card.whyWorthSeeingZh is None for card in artifact.previewItems)


@pytest.mark.asyncio
async def test_copy_transport_failure_is_not_a_semantic_systemic_failure(tmp_path, monkeypatch):
    from app.services.rardar_llm_control import RardarLLMError

    class CopyTimeout(ShadowDouble):
        async def __call__(self, **kwargs):
            if kwargs["scene"] == RardarLLMScene.WORTH_SEEING_COPY:
                raise RardarLLMError("rardar_llm_timeout", classification="timeout")
            return await super().__call__(**kwargs)

    monkeypatch.setattr(__name__ + ".ShadowDouble", CopyTimeout)
    _mirror, _run, _ledger, _double, artifact, _pool = await prepare(tmp_path, monkeypatch)
    assert artifact.reviewable and artifact.previewCount == 6
    assert artifact.audit["systemicProviderFailure"] is False


@pytest.mark.asyncio
async def test_failed_gate_remains_in_cohort_and_never_refills(tmp_path, monkeypatch):
    from app.services.rardar_llm_control import RardarLLMError

    class GateFailure(ShadowDouble):
        async def __call__(self, **kwargs):
            payload = json.loads(kwargs["messages"][1]["content"])
            if (
                payload.get("repository") == "fixture-lab/tool-100"
                and kwargs["scene"] == RardarLLMScene.WORTH_SEEING_GATE
            ):
                raise RardarLLMError("rardar_llm_timeout", classification="timeout")
            return await super().__call__(**kwargs)

    monkeypatch.setattr(__name__ + ".ShadowDouble", GateFailure)
    _mirror, _run, _ledger, _double, artifact, _pool = await prepare(tmp_path, monkeypatch)
    assert {a.candidate.githubRepositoryId for a in artifact.assessments} == set(range(100, 116))
    assert artifact.cohortAssessed == 16
    failed = next(a for a in artifact.assessments if a.candidate.githubRepositoryId == 100)
    assert failed.semanticDecision == "UNCERTAIN" and failed.failureCode == "provider_timeout"


@pytest.mark.asyncio
async def test_fifteen_terminal_results_are_incomplete_not_empty(tmp_path, monkeypatch):
    _mirror, _run, _ledger, _double, artifact, _pool = await prepare(tmp_path, monkeypatch, weak=True)
    payload = artifact.model_dump(mode="json")
    removed = payload["assessments"].pop()
    payload["nonPreviewItems"].remove(removed["candidate"]["githubRepositoryId"])
    payload["semanticDecisionCounts"][removed["semanticDecision"]] -= 1
    payload.update(cohortAssessed=15, cohortStructuredSuccess=15, shadowReviewState="incomplete", reviewable=False)
    payload["digest"] = digest({k: v for k, v in payload.items() if k != "digest"})
    partial = ShadowReviewArtifact.model_validate_json(json.dumps(payload), strict=True)
    assert not partial.reviewable and partial.shadowReviewState == "incomplete"


@pytest.mark.asyncio
async def test_budget_exhaustion_preserves_receipts_and_produces_incomplete(tmp_path, monkeypatch):
    from app.services.rardar_llm_control import RardarLLMError

    class Exhausted(ShadowDouble):
        async def __call__(self, **kwargs):
            payload = json.loads(kwargs["messages"][1]["content"])
            if not payload["repository"].startswith("negative-control/"):
                raise RardarLLMError("provider_budget_exhausted", classification="budget")
            return await super().__call__(**kwargs)

    monkeypatch.setattr(__name__ + ".ShadowDouble", Exhausted)
    _mirror, run, _ledger, _double, artifact, _pool = await prepare(tmp_path, monkeypatch)
    assert artifact.shadowReviewState == "incomplete" and not artifact.reviewable
    assert artifact.cohortAssessed == 0 and artifact.previewCount == 0
    assert (run / "stage-receipts" / "negative-1.json").exists()


@pytest.mark.asyncio
async def test_freeze_rejects_source_or_profile_drift_without_replacement(tmp_path, monkeypatch):
    from app.integrations.rardar import shadow_cohort

    mirror, _run, _ledger, _double, _artifact, pool = await prepare(tmp_path, monkeypatch)
    _target, source = _source(tmp_path)
    monkeypatch.setattr(shadow_cohort, "healthy_pool", lambda *_: (source, [row.candidate for row in pool], pool))
    target = tmp_path / "freeze"
    first = shadow_cohort.freeze(mirror, target)
    assert shadow_cohort.freeze(mirror, target) == first
    before = (target / "shadow-review-cohort-manifest.json").read_bytes()
    changed = [replace(pool[0], file_digest="b" * 64), *pool[1:]]
    monkeypatch.setattr(shadow_cohort, "healthy_pool", lambda *_: (source, [row.candidate for row in changed], changed))
    with pytest.raises(ShadowIntegrityError, match="freeze_conflict"):
        shadow_cohort.freeze(mirror, target)
    assert (target / "shadow-review-cohort-manifest.json").read_bytes() == before
