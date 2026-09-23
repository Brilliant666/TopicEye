"""The private correction path does not rewrite scheduled retry history."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.config import settings
from app.services import rardar_daily_operations, rardar_llm_control, rardar_material_correction, rardar_trending
from app.services.llm import daily_provider_budget


@pytest.fixture
def correction(tmp_path, monkeypatch):
    target = tmp_path / "data"
    target.mkdir()
    runtime = tmp_path / "runtime"
    monkeypatch.setattr(settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(target))
    monkeypatch.setattr(rardar_daily_operations, "operation_root", lambda: runtime)
    name = "albert-weasker/niubigeo"
    project = {
        "repository": name,
        "projectId": "albert-weasker-niubigeo--fixture",
        "materialState": "partial",
        "displayProfile": None,
        "profile": {"summary": "已有有效简介", "positioning": None},
    }
    monkeypatch.setattr(rardar_trending, "saved_materials", lambda _: {})
    monkeypatch.setattr(
        rardar_trending,
        "_history_with_materials",
        lambda *_: {"projects": [project], "generationId": "fixture-generation"},
    )
    monkeypatch.setattr(
        daily_provider_budget,
        "daily_execution_budget",
        AsyncMock(return_value=(SimpleNamespace(snapshot=lambda: {"remaining": 90}), {})),
    )
    monkeypatch.setattr(
        rardar_llm_control,
        "resolve_rardar_route_identity",
        AsyncMock(return_value="fixture-route"),
    )

    class FakeClient:
        def __init__(self):
            self.event_hooks = {"request": []}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

    monkeypatch.setattr(rardar_material_correction, "github_material_client", lambda *_: FakeClient())
    return SimpleNamespace(name=name, project=project, runtime=runtime, target=target)


@pytest.mark.asyncio
async def test_correction_is_allowlisted_one_use_and_preserves_daily_failure_record(correction, monkeypatch):
    async def collect(_target, project, _generation, client, _route):
        for hook in client.event_hooks["request"]:
            await hook(object())
        project.update(
            materialState="complete",
            displayProfile={"qualityState": "ready"},
            profile={"summary": "简介", "positioning": "有证据支持的核心定位"},
        )
        return SimpleNamespace(
            profile=SimpleNamespace(model_dump=lambda **_: {"repository": correction.name}, qualityState="ready"),
            evidence=object(),
        )

    monkeypatch.setattr(rardar_trending, "_collect_project_material", collect)
    monkeypatch.setattr(
        rardar_trending, "project_material", lambda *_: {"material": {"sourceRevision": "evidence-sha"}}
    )
    daily = correction.runtime / "2026-09-23-refocus-v1.json"
    daily.parent.mkdir(parents=True)
    daily.write_text('{"failures":2}', encoding="utf-8")

    first = await rardar_material_correction.apply_once(correction.name)
    second = await rardar_material_correction.apply_once(correction.name)

    assert first["status"] == "completed"
    assert first["sourceRequests"] == 1
    assert first["providerRequests"] == 0
    assert second["status"] == "already_attempted"
    assert daily.read_text(encoding="utf-8") == '{"failures":2}'


@pytest.mark.asyncio
async def test_failed_correction_keeps_one_use_receipt_without_a_second_dispatch(correction, monkeypatch):
    calls = 0

    async def fail(*_):
        nonlocal calls
        calls += 1
        raise ValueError("profile_evidence_incomplete")

    monkeypatch.setattr(rardar_trending, "_collect_project_material", fail)
    first = await rardar_material_correction.apply_once(correction.name)
    second = await rardar_material_correction.apply_once(correction.name)

    assert first["status"] == "failed"
    assert first["errorCode"] == "ValueError"
    assert second["status"] == "already_attempted"
    assert calls == 1


@pytest.mark.asyncio
async def test_unapproved_correction_is_rejected_before_creating_runtime_state(correction):
    with pytest.raises(ValueError, match="repository_not_allowed"):
        await rardar_material_correction.apply_once("jev-chat/jev-chat-jarvis")
    assert not correction.runtime.exists()
