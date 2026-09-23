"""One operator grant consumes one bounded correction, not daily retry history."""

import hashlib
from datetime import UTC, datetime, timedelta
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
    runtime.mkdir()
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
    monkeypatch.setattr(rardar_trending, "saved_materials", lambda *_a, **_k: {})
    monkeypatch.setattr(
        rardar_trending,
        "_history_with_materials",
        lambda *_a, **_k: {"projects": [project], "generationId": "fixture-generation"},
    )
    monkeypatch.setattr(
        daily_provider_budget,
        "daily_execution_budget",
        AsyncMock(return_value=(SimpleNamespace(snapshot=lambda: {"remaining": 90}), {})),
    )
    monkeypatch.setattr(rardar_llm_control, "resolve_rardar_route_identity", AsyncMock(return_value="fixture-route"))

    async def plan(_name, *, mode="generate"):
        return {
            "planDigest": "a" * 64,
            "projectId": project["projectId"],
            "repository": name,
            "priorReceiptSha256": None,
            "state": "incomplete",
            "mode": mode,
            "cachePlanDigest": "b" * 64,
        }

    monkeypatch.setattr(rardar_material_correction, "preview", plan)

    class FakeClient:
        def __init__(self):
            self.event_hooks = {"request": []}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

    monkeypatch.setattr(rardar_material_correction, "github_material_client", lambda *_: FakeClient())
    return SimpleNamespace(name=name, project=project, runtime=runtime, target=target)


def grant(correction, *, auth="niubigeo-fix-20260923", mode="generate", maximum=6):
    now = datetime.now(UTC)
    return {
        "schemaVersion": 1,
        "authorizationId": auth,
        "repository": correction.name,
        "projectId": correction.project["projectId"],
        "mode": mode,
        "maxProviderRequests": maximum,
        "priorReceiptSha256": None,
        "approvedPlanDigest": "a" * 64,
        "approvedAt": (now - timedelta(minutes=1)).isoformat(),
        "expiresAt": (now + timedelta(hours=1)).isoformat(),
        "reason": "approved focused correction after validated diagnostic fix",
    }


@pytest.mark.asyncio
async def test_correction_is_one_use_and_preserves_daily_failure_record(correction, monkeypatch):
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
    daily.parent.mkdir(parents=True, exist_ok=True)
    daily.write_text('{"failures":2}', encoding="utf-8")

    authorization = grant(correction)
    first = await rardar_material_correction.apply_once(
        correction.name,
        mode="generate",
        expected_plan_digest="a" * 64,
        operator_grant=authorization,
    )

    async def preview_must_not_repeat(*_a, **_k):
        raise AssertionError("repeat must read the immutable receipt before a changed production plan")

    monkeypatch.setattr(rardar_material_correction, "preview", preview_must_not_repeat)
    second = await rardar_material_correction.apply_once(
        correction.name,
        mode="generate",
        expected_plan_digest="a" * 64,
        operator_grant=authorization,
    )

    assert first["status"] == "completed"
    assert first["sourceRequests"] == 1
    assert first["providerRequests"] == 0
    assert second["status"] == "already_attempted"
    assert daily.read_text(encoding="utf-8") == '{"failures":2}'


@pytest.mark.asyncio
async def test_failed_correction_keeps_receipt_without_second_dispatch(correction, monkeypatch):
    calls = 0

    async def fail(*_):
        nonlocal calls
        calls += 1
        raise ValueError("profile_evidence_incomplete")

    monkeypatch.setattr(rardar_trending, "_collect_project_material", fail)
    authorization = grant(correction)
    first = await rardar_material_correction.apply_once(
        correction.name,
        mode="generate",
        expected_plan_digest="a" * 64,
        operator_grant=authorization,
    )
    second = await rardar_material_correction.apply_once(
        correction.name,
        mode="generate",
        expected_plan_digest="a" * 64,
        operator_grant=authorization,
    )
    assert first["status"] == "failed"
    assert first["errorCode"] == "ValueError"
    assert second["status"] == "already_attempted"
    assert calls == 1


@pytest.mark.asyncio
async def test_invalid_grant_and_stale_plan_never_create_receipt(correction):
    authorization = grant(correction)
    authorization["repository"] = "other/project"
    with pytest.raises(ValueError, match="grant_scope_mismatch"):
        await rardar_material_correction.apply_once(
            correction.name,
            mode="generate",
            expected_plan_digest="a" * 64,
            operator_grant=authorization,
        )
    with pytest.raises(ValueError, match="plan_stale"):
        await rardar_material_correction.apply_once(
            correction.name,
            mode="generate",
            expected_plan_digest="f" * 64,
            operator_grant=grant(correction),
        )
    assert not (correction.runtime / "material-corrections-v2").exists()


@pytest.mark.asyncio
async def test_cache_only_uses_same_grant_without_provider(correction, monkeypatch):
    from app.services import rardar_cache_reassembly

    applied = 0

    async def cache_apply(_name, _digest):
        nonlocal applied
        applied += 1
        return {"materialState": "complete", "profileRevision": "r1", "sourceGeneration": "g1"}

    monkeypatch.setattr(rardar_cache_reassembly, "apply_locked", cache_apply)
    authorization = grant(correction, mode="cache-only", maximum=0)
    first = await rardar_material_correction.apply_once(
        correction.name,
        mode="cache-only",
        expected_plan_digest="a" * 64,
        operator_grant=authorization,
    )
    second = await rardar_material_correction.apply_once(
        correction.name,
        mode="cache-only",
        expected_plan_digest="a" * 64,
        operator_grant=authorization,
    )
    assert first["status"] == "completed"
    assert first["providerRequests"] == first["sourceRequests"] == 0
    assert second["status"] == "already_attempted"
    assert applied == 1


@pytest.mark.asyncio
async def test_new_grant_is_bound_to_immutable_old_receipt(correction, monkeypatch):
    old = correction.runtime / "material-corrections-v1" / "albert-weasker--niubigeo.json"
    old.parent.mkdir()
    old.write_bytes(b'{"status":"failed","providerRequests":2}')
    old_digest = hashlib.sha256(old.read_bytes()).hexdigest()

    async def plan(_name, *, mode="generate"):
        return {
            "planDigest": "a" * 64,
            "projectId": correction.project["projectId"],
            "repository": correction.name,
            "priorReceiptSha256": old_digest,
            "state": "incomplete",
            "mode": mode,
        }

    monkeypatch.setattr(rardar_material_correction, "preview", plan)
    invalid = grant(correction)
    with pytest.raises(ValueError, match="grant_scope_mismatch"):
        await rardar_material_correction.apply_once(
            correction.name,
            mode="generate",
            expected_plan_digest="a" * 64,
            operator_grant=invalid,
        )
    assert old.read_bytes() == b'{"status":"failed","providerRequests":2}'
    assert not (correction.runtime / "material-corrections-v2").exists()
