"""Fixed semantic rejections survive the collector and durable diagnostics; no Provider IO."""

import json
import subprocess
import sys
from types import SimpleNamespace

import httpx
import pytest

from app.integrations.rardar import serving_profiles as profiles
from app.services.rardar_material_diagnostics import material_failure_diagnostic
from tests_rardar_llm.test_serving_profiles import _project, _readme_payload

ROLE_RULE = "profile_serving_v6_positioning_requires_a_mechanism_or_primary_outcome"


@pytest.mark.parametrize("source", ["official_zh", "official_translated", "rardar_derived"])
@pytest.mark.parametrize("rule", ["text_invalid", "evidence_invalid", "identity_duplicate", ROLE_RULE])
def test_semantic_candidate_failure_is_not_reported_as_provider_unavailable(source, rule):
    code = f"positioning_candidate_{source}_{rule}"
    assert profiles._stable_profile_failure([profiles.ProfileGenerationFailure("positioning", code, False)]) == (
        "profile_model_invalid_output",
        "positioning",
    )


@pytest.mark.parametrize("code", ["positioning_timeout", "positioning_provider_error", "positioning_rate_limited"])
def test_actual_provider_failure_retains_unavailable_classification(code):
    assert profiles._stable_profile_failure([profiles.ProfileGenerationFailure("positioning", code, False)]) == (
        "profile_model_unavailable",
        "positioning",
    )


def test_unknown_positioning_failure_does_not_invent_provider_fault():
    assert profiles._stable_profile_failure([profiles.ProfileGenerationFailure("positioning", "unknown", False)]) == (
        "profile_unknown_failure",
        "positioning",
    )


def test_fixed_candidate_reason_survives_durable_diagnostic_without_untrusted_text(tmp_path):
    code = f"positioning_candidate_official_translated_{ROLE_RULE}"
    failure = profiles.ProfileGenerationFailure("positioning", code, False)
    untrusted = profiles.ProfileGenerationFailure("positioning", "positioning_candidate_secret_token=private", False)
    diagnostic = material_failure_diagnostic(
        ValueError("private outer error"),
        project={"projectId": "fixture-project"},
        stage="profile",
        collected=SimpleNamespace(generation_failures=(failure, untrusted), profile=None),
    )
    path = tmp_path / "diagnostic.json"
    path.write_text(json.dumps(diagnostic), encoding="utf-8")
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["generationFailures"][0]["code"] == code
    assert saved["generationFailures"][1]["code"] == "unknown"
    assert "secret_token" not in json.dumps(saved)
    assert "private outer" not in json.dumps(saved)
    replay = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json,socket,sys; "
            "socket.socket.connect=lambda *_a,**_k: (_ for _ in ()).throw(AssertionError('network forbidden')); "
            "from app.integrations.rardar.serving_profiles import ProfileGenerationFailure,_stable_profile_failure; "
            "v=json.load(open(sys.argv[1],encoding='utf-8'))['generationFailures'][0]; "
            "print(json.dumps(_stable_profile_failure([ProfileGenerationFailure(v['stage'],v['code'],v['resolved'])])))",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    assert json.loads(replay.stdout) == ["profile_model_invalid_output", "positioning"]


@pytest.mark.asyncio
async def test_actual_collector_records_fixed_semantic_rejection_not_provider_outage(tmp_path, monkeypatch):
    """Synthetic same-shape failure, not a reconstruction of a lost historical response."""
    project = _project().model_copy(update={"repository": "fixture-lab/semantic-rejection", "description": None})
    markdown = """
# 官方资料工具

**一个整理公开仓库证据的工具。**

这是一套基于 Node.js 的渲染系统，通过原始资料索引生成项目地图。

- **读取资料** —— 索引仓库官方说明
- **核对来源** —— 对照固定版本中的引用
- **输出地图** —— 生成静态项目地图

## 快速开始
"""
    code = f"positioning_candidate_official_zh_{ROLE_RULE}"
    monkeypatch.setattr(profiles, "_select_positioning_candidate", lambda *_a, **_kw: (None, [code]))

    def handler(request):
        if request.url.path.endswith("/contents"):
            return httpx.Response(200, json=[{"path": "README_ZH.md", "type": "file"}])
        return httpx.Response(200, json=_readme_payload(markdown, path="README_ZH.md", sha="8" * 40))

    async def deny_model(*_a, **_kw):
        raise AssertionError("Provider request forbidden")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com") as client:
        collected = await profiles.collect_official_project_profile(
            project,
            "synthetic-semantic-rejection",
            tmp_path,
            client=client,
            translate=True,
            allow_model_generation=False,
            model_route_identity="a" * 64,
            translator=deny_model,
            narrative_translator=deny_model,
            positioning_translator=deny_model,
            save_partial_introduction=True,
        )
    assert collected.profile.positioningZh is None
    assert collected.profile.profileState == "partial"
    assert collected.profile_cache_state == "unavailable"
    assert collected.translation_calls == 0
    failure = next(item for item in collected.generation_failures if item.code == code)
    assert failure.diagnostic["classification"] == "semantic_invalid"
    assert failure.diagnostic["ruleCode"] == ROLE_RULE
    assert failure.diagnostic["inputDigest"] == collected.evidence.digest
    assert collected.profile_failure_code == "profile_model_invalid_output"
    diagnostic = material_failure_diagnostic(
        ValueError("outer projector rejected missing positioning"),
        project={"projectId": "fixture-project"},
        stage="profile",
        collected=collected,
    )
    saved = json.loads(json.dumps(diagnostic))
    item = next(item for item in saved["generationFailures"] if item["code"] == code)
    assert item["detail"]["validationStage"] == "semantic"
    assert item["detail"]["fieldPath"] == "$.positioningIncludedRoles"
    assert item["detail"]["sourceMode"] == "official_zh"
    assert item["detail"]["ruleCode"] == ROLE_RULE
