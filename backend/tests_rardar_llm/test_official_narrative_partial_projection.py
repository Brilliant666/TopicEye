"""Synthetic collector regression for a rejected final positioning, no model IO."""

import httpx
import pytest
from pydantic import ValidationError

from app.integrations.rardar import project_introductions, serving_profiles as profiles
from tests_rardar_llm.test_serving_profiles import _project, _readme_payload


@pytest.mark.asyncio
async def test_rejected_positioning_does_not_claim_complete_official_narrative(tmp_path, monkeypatch):
    project = _project().model_copy(update={"repository": "fixture-lab/author-first", "description": None})
    markdown = """
# 作者优先项目

**把公开仓库证据整理成可验证、可交付的项目地图。**

这是一套基于 Node.js 的渲染与校验系统，由 Agent 生成 Typed JSON IR，再确定性编译为独立 HTML。

- **打开就是成品** —— 生成可交互的独立 HTML 文件
- **合并前看清变化** —— 对比两份经过校验的架构快照
- **每次探索都有依据** —— 所有结论都回指版本化源码
- **一个文件放心交付** —— 同时支持 HTML、PNG 与 SVG

## 快速开始
"""
    assert profiles._extract_official_narrative(markdown, "README_ZH.md", None).mature
    # Reproduce the validated selector's no-acceptable-candidate outcome seen
    # in the captured repository; no validator or evidence rule is bypassed.
    monkeypatch.setattr(profiles, "_select_positioning_candidate", lambda *_a, **_kw: (None, []))

    def handler(request):
        if request.url.path.endswith("/contents"):
            return httpx.Response(200, json=[{"path": "README_ZH.md", "type": "file"}])
        return httpx.Response(200, json=_readme_payload(markdown, path="README_ZH.md", sha="6" * 40))

    async def deny_model(*_a, **_kw):
        raise AssertionError("model request forbidden")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com") as client:
        collected = await profiles.collect_official_project_profile(
            project,
            "synthetic-partial",
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
    profile = collected.profile
    assert profile.profileState == "partial"
    assert profile.officialNarrativeMode == "rardar_derived"
    assert profile.sourceLabel == "Rardar 整理"
    assert profile.officialPositioningZh is None and profile.positioningEvidenceRefs == []
    assert profile.officialTaglineZh and profile.officialHighlights
    assert all(
        item.sourceTitle == item.titleZh and item.sourceDetail == item.detailZh for item in profile.officialHighlights
    )
    assert all(item.sourceMode == "official_zh" for item in profile.capabilities)
    assert not profiles._profile_is_publishable(profile)
    assert collected.profile_cache_state == "unavailable"
    assert collected.translation_calls == 0
    assert all(ref in collected.evidence.evidenceIndex for refs in profile.claimEvidenceRefs.values() for ref in refs)
    saved = project_introductions.saved(tmp_path)
    assert saved[project.repository]["summary"] == profile.officialTaglineZh
    assert not list((tmp_path / "profile-store").glob("**/*.json"))
    damaged = profile.model_dump(mode="json")
    damaged["officialHighlights"][0]["evidenceRefs"] = []
    with pytest.raises(ValidationError):
        type(profile).model_validate(damaged)
