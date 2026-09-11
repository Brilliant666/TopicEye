"""Synthetic saved insights over validated fixture Profile/Evidence, no Provider."""

import json
import threading
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from app.integrations.rardar import material_trait_revision as revision
from app.integrations.rardar.profile_cache_v2 import ProfileStoreEnvelopeV2
from app.schemas.rardar_product import ProjectExplanation, ProjectExplanationResponse, SharedProjectInsightRequest
from app.services import rardar_project_insights as insight, rardar_trending as materials
from tests_rardar_llm.test_managed_materials import seed
from tests_rardar_llm.test_product import _insight


@pytest_asyncio.fixture
async def saved(tmp_path, monkeypatch):
    path = await seed(tmp_path)
    envelope = ProfileStoreEnvelopeV2.model_validate_json(path.read_bytes(), strict=True)
    original = envelope.profile.model_copy(
        update={
            "productFormsZh": ["服务"],
            "claimEvidenceRefs": {**envelope.profile.claimEvidenceRefs, "服务": ["description"]},
        }
    )
    retained = [SimpleNamespace(profile=original, evidence=envelope.evidence, project=None)]
    monkeypatch.setattr(materials, "_retained_serving_details", lambda _: retained)
    monkeypatch.setattr(insight.settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(insight, "resolve_rardar_route_identity", AsyncMock(return_value="fixture-route"))
    insight._RUNNING.clear()
    insight._LAST_STATE.clear()

    def project(*_args):
        return {
            **materials.saved_materials(tmp_path)[original.repository],
            "projectId": "fixture-id",
            "generationId": "fixture-board",
        }

    monkeypatch.setattr(insight, "_project", project)
    model = AsyncMock(side_effect=AssertionError("saved read must not invoke model"))
    collect = AsyncMock(side_effect=AssertionError("saved read must not collect"))
    monkeypatch.setattr(insight, "_explain_project_with_evidence", model)
    monkeypatch.setattr(insight, "collect_project_evidence", collect)
    evidence = insight._material_evidence(project())
    payload = _insight().model_dump(mode="json")
    reference, start_path = next(iter(evidence.path_refs.items()))

    def bind(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "evidenceRefs":
                    value[key] = [reference]
                else:
                    bind(child)
        elif isinstance(value, list):
            for child in value:
                bind(child)

    bind(payload)
    payload["startHere"][0]["path"] = start_path
    result = ProjectExplanationResponse(
        state="ready",
        repository=original.repository,
        githubRepositoryId=original.githubRepositoryId,
        generationId="original-analysis-generation",
        promptVersion=insight._PROJECT_PROMPT_VERSION,
        schemaVersion=insight._PROJECT_SCHEMA_VERSION,
        format="structured",
        officialIntro=evidence.official_intro,
        analysis=ProjectExplanation.model_validate_json(json.dumps(payload), strict=True),
        evidenceDigest=evidence.digest,
        evidenceKinds=["fixture-saved-material"],
    )
    insight._validate_project_insight(result.analysis, evidence)
    cache_path = await insight._cache_path(project(), evidence)
    cache_path.parent.mkdir(parents=True)
    result_payload = result.model_dump(mode="json")
    insight.atomic(cache_path, {"schemaVersion": 1, "result": result_payload, "digest": insight.digest(result_payload)})
    return SimpleNamespace(
        target=tmp_path,
        profile=original,
        evidence=envelope.evidence,
        retained=retained,
        project=project,
        result=result,
        cache=cache_path,
        model=model,
        collect=collect,
    )


def request():
    return SharedProjectInsightRequest(generationId="fixture-board", context="historical_hot")


@pytest.mark.asyncio
async def test_display_trait_revision_preserves_exact_original_insight_and_read_is_zero_call(saved):
    initial = await insight.read_project_insight("fixture-id", request())
    assert initial.state == "ready"
    assert revision.install(saved.target, saved.profile, saved.evidence)["changed"]
    assert saved.project()["displayProfile"] != saved.profile.model_dump(mode="json")
    before = {p: p.read_bytes() for p in saved.target.rglob("*.json")}
    insight._material_evidence(saved.project())
    restored = await insight.read_project_insight("fixture-id", request())
    assert restored.state == "ready" and restored.result.cacheHit
    assert restored.result.evidenceDigest == initial.result.evidenceDigest
    assert restored.result.generationId == "original-analysis-generation"
    assert restored.result.analysis == initial.result.analysis
    assert {p: p.read_bytes() for p in saved.target.rglob("*.json")} == before
    repeated = await insight.start_project_insight("fixture-id", request())
    assert repeated.state == "ready" and repeated.result.cacheHit
    saved.model.assert_not_awaited()
    saved.collect.assert_not_awaited()


@pytest.mark.asyncio
async def test_real_profile_content_change_does_not_reuse_original_insight(saved):
    revision.install(saved.target, saved.profile, saved.evidence)
    changed_text = "新增资料说明，不能当成旧解读已经处理的内容。"
    changed = saved.profile.model_copy(
        update={
            "generatedAt": saved.profile.generatedAt + timedelta(seconds=1),
            "rardarAssessmentZh": changed_text,
            "rardarAssessmentEvidenceRefs": ["description"],
            "coreValueZh": changed_text,
            "coreValueEvidenceRefs": ["description"],
            "claimEvidenceRefs": {**saved.profile.claimEvidenceRefs, changed_text: ["description"]},
        }
    )
    saved.retained.append(SimpleNamespace(profile=changed, evidence=saved.evidence, project=None))
    # An exact original lookup is independent of which newer Profile is latest.
    exact = materials.load_saved_project_profile(
        saved.target,
        saved.profile.repository,
        original_profile_digest=revision.digest(saved.profile.model_dump(mode="json")),
    )
    assert exact[0] == saved.profile
    assert (await insight.read_project_insight("fixture-id", request())).state == "unprocessed"
    saved.model.assert_not_awaited()
    saved.collect.assert_not_awaited()


@pytest.mark.asyncio
async def test_material_reads_do_not_block_the_event_loop(saved, monkeypatch):
    original = insight._material_evidence
    event_thread = threading.get_ident()
    called = []

    def read(*args, **kwargs):
        called.append(threading.get_ident())
        return original(*args, **kwargs)

    monkeypatch.setattr(insight, "_material_evidence", read)
    assert (await insight.read_project_insight("fixture-id", request())).state == "ready"
    assert (await insight.start_project_insight("fixture-id", request())).result.cacheHit
    assert len(called) == 2 and all(thread != event_thread for thread in called)
    saved.model.assert_not_awaited()


@pytest.mark.asyncio
async def test_revision_cannot_substitute_a_different_original_profile(saved, monkeypatch):
    revision.install(saved.target, saved.profile, saved.evidence)
    displayed = saved.project()
    saved.retained.clear()  # the remaining cache contains a different original Profile
    monkeypatch.setattr(insight, "_project", lambda *_: displayed)
    result = await insight.read_project_insight("fixture-id", request())
    assert result.state == "unavailable" and result.errorCode == "project_insight_material_invalid"
    saved.model.assert_not_awaited()
    saved.collect.assert_not_awaited()
