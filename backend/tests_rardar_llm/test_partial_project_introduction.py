"""Partial introductions retain their own evidence, not relaxed Profile gates."""

import base64
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.config import settings
from app.integrations.rardar import project_introductions as intro, serving_profiles, trending_store
from app.integrations.rardar.profile_cache_v2 import ProfileStoreEnvelopeV2
from app.integrations.rardar.serving_schemas import OfficialProjectProfile
from app.services import rardar_llm_control, rardar_trending as service
from app.services.llm import daily_provider_budget
from tests_rardar_llm.test_rardar_trending_store import board
from tests_rardar_selection.test_profile_cache_v2 import _handler, _project


@pytest.mark.asyncio
async def test_valid_zh_intro_survives_incomplete_profile_and_reads_all_contexts(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(serving_profiles, "_profile_quality", lambda **_: ("rejected", ["capability_missing"]))
    project = _project().model_copy(update={"description": ""})
    source = board("github", [project.repository])
    source["entries"][0]["reportedDelta"] = 200
    installed = trending_store.publish_sources(tmp_path, [source])
    pointer = (tmp_path / "trending-boards/current.json").read_bytes()
    async with httpx.AsyncClient(
        base_url="https://api.github.com", transport=httpx.MockTransport(_handler([]))
    ) as client:
        collected = await serving_profiles.collect_official_project_profile(
            project,
            "actual-test-generation",
            tmp_path / "profile-cache",
            client=client,
            translate=True,
            allow_model_generation=False,
            model_route_identity="a" * 64,
            save_partial_introduction=True,
        )
    assert collected.profile_cache_state == "unavailable"
    assert collected.profile.qualityState == "rejected"
    assert collected.translation_calls == 0
    values = intro.saved(tmp_path / "profile-cache")
    value = values[project.repository.lower()]
    assert value["summary"] and value["sourceMode"] == "official_zh"
    assert value["generatedAt"] is None  # no invented model-generation date
    service.publish_history_review(tmp_path, trigger="manual_initialization")
    rows = [service.today()["projects"][0], service.history()["projects"][0]]
    rows += [
        service.detail(rows[0]["projectId"], installed["generationId"]),
        service.detail(rows[0]["projectId"], None, historical=True),
    ]
    assert all(r["profile"]["summary"] == value["summary"] for r in rows)
    assert all(r["materialState"] == "partial" and r.get("displayProfile") is None for r in rows)
    assert all("displayProfile" not in r and r["displayCard"] is None for r in rows[:2])
    assert service.load_saved_project_profile(tmp_path, project.repository) is None
    assert (tmp_path / "trending-boards/current.json").read_bytes() == pointer
    again = intro.save(
        tmp_path / "profile-cache",
        collected.evidence,
        value["summary"],
        value["evidenceRefs"],
        source_mode="official_zh",
        source_label=value["sourceLabel"],
    )
    assert again == value
    with pytest.raises(ValueError):
        intro.save(
            tmp_path / "profile-cache",
            collected.evidence,
            "一个没有任何资料支持的虚构能力说明。",
            ["missing"],
            source_mode="official_zh",
            source_label="官方",
        )
    assert intro.saved(tmp_path / "profile-cache") == values
    path = next((tmp_path / "profile-cache/introductions").glob("*/*.json"))
    record = json.loads(path.read_bytes())
    record["payload"]["summary"] = "这是被损坏缓存擅自替换的项目介绍。"
    path.write_text(json.dumps(record), encoding="utf-8")
    assert intro.saved(tmp_path / "profile-cache") == {}


@pytest.mark.asyncio
async def test_partial_intro_does_not_finish_daily_profile_work(tmp_path, monkeypatch):
    (tmp_path / "trending-boards").mkdir()
    project = {
        "repository": "org/example",
        "projectId": "example",
        "materialState": "partial",
        "profile": {"summary": "有依据的中文简介", "generatedAt": None},
        "totalStars": 0,
        "appearances": [{"source": "github", "reportedDelta": 200, "fetchedAt": datetime.now(UTC).isoformat()}],
    }
    monkeypatch.setattr(service, "saved_materials", lambda _: {})
    monkeypatch.setattr(service, "_history_with_materials", lambda *_: {"projects": [project], "generationId": "g"})
    monkeypatch.setattr(service, "load_snapshot", lambda _: {"projects": [project]})
    monkeypatch.setattr(
        daily_provider_budget,
        "daily_execution_budget",
        AsyncMock(return_value=(SimpleNamespace(snapshot=lambda: {"remaining": 80}), {})),
    )
    monkeypatch.setattr(rardar_llm_control, "resolve_rardar_route_identity", AsyncMock(return_value="same-route"))
    collector = AsyncMock(side_effect=ValueError("unavailable"))
    monkeypatch.setattr(service, "_collect_project_material", collector)
    result = await service.historical_work(tmp_path, {}, lambda: None)
    assert collector.await_count == 1 and result["failed"] == 1 and result["remaining"] == 1
    assert project["profile"]["summary"] == "有依据的中文简介"


@pytest.mark.asyncio
async def test_full_profile_still_wins_over_partial_introduction(tmp_path):
    from app.integrations.rardar.profile_cache_v2 import ProfileStoreEnvelopeV2
    from tests_rardar_llm.test_managed_materials import seed

    path = await seed(tmp_path)
    record = ProfileStoreEnvelopeV2.model_validate_json(path.read_bytes(), strict=True)
    summary = record.profile.identitySummaryZh
    intro.save(
        tmp_path / "profile-cache",
        record.evidence,
        summary,
        record.profile.claimEvidenceRefs[summary],
        source_mode="validated_translation",
        source_label="测试响应",
        generated_at=datetime.now(UTC).isoformat(),
    )
    material = service.saved_materials(tmp_path)[record.profile.repository.lower()]
    assert material["displayProfile"] == record.profile.model_dump(mode="json")


@pytest.mark.asyncio
async def test_evidence_bound_partial_positioning_reads_cards_and_detail_without_fake_generation(tmp_path, monkeypatch):
    from tests_rardar_llm.test_managed_materials import seed

    fixture_path = await seed(tmp_path / "fixture")
    fixture = ProfileStoreEnvelopeV2.model_validate_json(fixture_path.read_bytes(), strict=True)
    data = fixture.profile.model_dump(mode="json")
    data.update(
        capabilities=[],
        capabilityBulletsZh=[],
        keyDifferentiators=[],
        rardarDifferentiators=[],
        coreValueZh=None,
        coreValueEvidenceRefs=[],
        rardarAssessmentZh=None,
        rardarAssessmentEvidenceRefs=[],
        qualityState="partial",
        qualityIssues=["capabilities_missing"],
    )
    partial = OfficialProjectProfile.model_validate_json(json.dumps(data), strict=True)
    assert partial.positioningZh and partial.positioningEvidenceRefs
    target = tmp_path / "live"
    monkeypatch.setattr(settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(target))
    project = _project()
    source = board("github", [project.repository])
    source["entries"][0]["reportedDelta"] = 200
    installed = trending_store.publish_sources(target, [source])
    summary = partial.identitySummaryZh
    saved = intro.save(
        target / "profile-cache",
        fixture.evidence,
        summary,
        partial.claimEvidenceRefs[summary],
        source_mode="validated_translation",
        source_label=partial.sourceLabel,
        generated_at=None,
        partial_profile=partial,
    )
    assert saved["schemaVersion"] == 2 and saved["generatedAt"] is None
    card = service.today()["projects"][0]
    detail = service.detail(card["projectId"], installed["generationId"])
    for row in (card, detail):
        assert row["materialState"] == "partial"
        assert row["profile"]["positioning"] == partial.positioningZh
        assert row["material"]["sourceKind"] == "partial_profile"
        assert row["material"]["generatedAt"] is None
    assert card["displayCard"]["positioningZh"] == partial.positioningZh
    assert detail["displayProfile"]["positioningZh"] == partial.positioningZh
    assert detail["displayProfile"]["positioningEvidenceRefs"] == partial.positioningEvidenceRefs
    assert detail["displayProfile"]["generatedAt"] is None
    assert detail["displayEvidence"]["digest"] == fixture.evidence.digest

    full_path = target / "selection-profile-cache/profile-store/v2" / fixture_path.parent.name / fixture_path.name
    full_path.parent.mkdir(parents=True)
    full_path.write_bytes(fixture_path.read_bytes())
    chosen = service.saved_materials(target, repositories={project.repository})[project.repository.lower()]
    assert chosen["materialState"] == "complete"
    assert chosen["displayProfile"]["positioningZh"] == fixture.profile.positioningZh


@pytest.mark.asyncio
async def test_collector_retains_valid_positioning_when_optional_capabilities_are_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(
        serving_profiles,
        "_valid_capabilities",
        lambda _capabilities, _allowed_refs: ([], ["capability_invalid_content"]),
    )
    project = _project()
    async with httpx.AsyncClient(
        base_url="https://api.github.com", transport=httpx.MockTransport(_handler([]))
    ) as client:
        collected = await serving_profiles.collect_official_project_profile(
            project,
            "partial-positioning-generation",
            tmp_path / "profile-cache",
            client=client,
            translate=True,
            allow_model_generation=False,
            model_route_identity="a" * 64,
            save_partial_introduction=True,
        )
    assert collected.profile.positioningZh is not None
    assert collected.profile.capabilities == []
    assert collected.profile_cache_state == "unavailable"
    saved = intro.saved(tmp_path / "profile-cache")[project.repository.lower()]
    assert saved["schemaVersion"] == 2
    assert saved["generatedAt"] is None
    visible = service.saved_materials(tmp_path, repositories={project.repository})[project.repository.lower()]
    assert visible["materialState"] == "partial"
    assert visible["displayProfile"]["positioningZh"] == collected.profile.positioningZh
    assert visible["displayProfile"]["generatedAt"] is None


@pytest.mark.asyncio
async def test_raw_invalid_optional_capability_flows_through_collector_to_cards_and_detail(tmp_path, monkeypatch):
    """The actual translator boundary must isolate a bad field before collector persistence."""
    monkeypatch.setattr(settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(tmp_path))
    project = _project().model_copy(
        update={
            "description": (
                "A tool that organizes project evidence into a traceable index, connecting "
                "original sources to decision rules so readers can verify conclusions."
            )
        }
    )
    source = board("github", [project.repository])
    source["entries"][0]["reportedDelta"] = 200
    installed = trending_store.publish_sources(tmp_path, [source])
    readme = base64.b64encode(b"# Evidence index\n").decode()
    source_requests: list[str] = []

    def source_handler(request: httpx.Request) -> httpx.Response:
        source_requests.append(request.url.path)
        if request.url.path.endswith("/contents"):
            return httpx.Response(200, json=[{"path": "README.md", "type": "file"}])
        return httpx.Response(
            200,
            json={"path": "README.md", "sha": "a" * 40, "encoding": "base64", "content": readme},
        )

    model_calls: list[dict] = []

    async def structured_model(**kwargs):
        model_calls.append(kwargs)
        raw = {
            "summary": {"text": "一款将项目证据整理为可追溯索引的工具。", "evidenceRefs": ["description"]},
            "positioning": {
                "positioningZh": "通过关联原始来源与判断规则形成可追溯索引，帮助读者核对项目结论。",
                "includedEvidenceRefs": ["description"],
                "includedRoles": ["core_mechanism", "primary_outcome"],
                "excludedClauses": [],
            },
            "capabilities": [
                {"title": "不可用能力", "detail": 42, "shortDetail": None, "evidenceRefs": ["description"]}
            ],
        }
        return SimpleNamespace(value=serving_profiles.CoreProfileTranslation.model_validate(raw, strict=True))

    monkeypatch.setattr(rardar_llm_control, "call_rardar_structured", structured_model)
    async with httpx.AsyncClient(
        base_url="https://api.github.com", transport=httpx.MockTransport(source_handler)
    ) as client:
        collected = await serving_profiles.collect_official_project_profile(
            project,
            installed["generationId"],
            tmp_path / "profile-cache",
            client=client,
            translate=True,
            model_route_identity="a" * 64,
            save_partial_introduction=True,
        )
    assert len(model_calls) == 1
    assert model_calls[0]["response_model"] is serving_profiles.CoreProfileTranslation
    assert collected.translation_calls == 1
    assert collected.profile.positioningZh is not None
    assert not collected.profile.capabilities
    assert collected.profile_cache_state == "unavailable"
    record = intro.saved(tmp_path / "profile-cache")[project.repository.lower()]
    assert record["schemaVersion"] == 2 and record["partialProfile"]["positioningZh"]
    card = service.today()["projects"][0]
    detail = service.detail(card["projectId"], installed["generationId"])
    assert card["displayCard"]["positioningZh"] == collected.profile.positioningZh
    assert detail["displayProfile"]["positioningZh"] == collected.profile.positioningZh
    assert detail["displayProfile"]["positioningEvidenceRefs"] == ["description"]
    assert card["materialState"] == detail["materialState"] == "partial"
    assert all(path.startswith("/repos/") for path in source_requests)
