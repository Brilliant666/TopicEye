"""README role selection, not repository-specific content or model generation."""

import json

import httpx
import pytest
import pytest_asyncio

from app.integrations.rardar import serving_profiles as profiles
from tests_rardar_llm.test_serving_profiles import _project, _readme_payload

MARKDOWN = """# PublicCollector

### Thanks to our sponsor

<small>OtherService 提供自动采集服务，立即免费试用。</small>

> **免责声明：**
> 本仓库仅供学习和研究，禁止用于商业用途。

## 项目简介

一个通过浏览器采集多个公开网站信息的数据工具，支持保存登录状态。

### 技术原理

- **核心技术**：基于浏览器上下文保存登录态并读取签名参数。
- **本地保存**：将取得的数据保存为本地文件。

## 功能特性

<details>
<summary>开源版不够用？看看 CollectorPro 多了什么</summary>

CollectorPro 相较于开源版本的核心优势：

- **商业版功能**：支持多账号轮换和断点续采。

</details>

## 使用方式

运行程序后选择需要读取的公开来源。
"""


def test_primary_text_skips_sponsor_and_disclaimer_and_uses_actual_overview():
    sections = profiles._parse_readme(MARKDOWN, "README.md")
    summary, ref, capabilities, *_ = profiles._source_claims(sections, None)
    assert summary == "一个通过浏览器采集多个公开网站信息的数据工具，支持保存登录状态。"
    assert summary in sections[int(ref.rsplit(":", 1)[1]) - 1].excerpts
    assert not any("商业版功能" in text for text in capabilities)
    narrative = profiles._extract_official_narrative(MARKDOWN, "README.md", None)
    assert narrative.tagline == summary
    assert narrative.positioning and "浏览器上下文" in narrative.positioning
    assert "免责声明" not in narrative.positioning


@pytest.mark.parametrize(
    "text",
    [
        "> 免责声明：本仓库仅供学习和研究，禁止用于商业用途。",
        "Disclaimer: this repository is for educational purposes only.",
        "Sponsored: AnotherService provides a hosted product. Start your free trial now.",
    ],
)
def test_administrative_or_sponsored_prose_is_not_official_positioning(text):
    assert not profiles._official_positioning_is_high_signal(text, "zh" if "仓库" in text else "en")


def test_legitimate_project_limits_are_not_removed():
    text = "这是一个用于法律研究的本地工具，通过索引公开法规提供查询，不提供法律意见。"
    assert profiles._official_positioning_is_high_signal(text, "zh")


@pytest.mark.parametrize("mode", ["official_zh", "official_translated", "rardar_derived"])
def test_every_positioning_source_rejects_disclaimer_even_when_it_mentions_outcome_words(mode):
    text = "免责声明：本仓库仅供学习和研究，禁止用于商业用途。"
    candidate = profiles._PositioningCandidate(
        text=text,
        evidence_refs=("readme:section:1",),
        source_mode=mode,
        included_roles=tuple(profiles._positioning_roles(text)),
    )
    assert (
        profiles._positioning_candidate_issue(
            candidate, identity="一个整理公开仓库资料的本地工具。", allowed_refs={"readme:section:1"}
        )
        is not None
    )


@pytest.mark.asyncio
async def test_collector_uses_chinese_source_without_model_or_paid_edition_claims(tmp_path):
    def handler(request):
        if request.url.path.endswith("/contents"):
            return httpx.Response(200, json=[{"path": "README.md", "type": "file"}])
        return httpx.Response(200, json=_readme_payload(MARKDOWN, sha="d" * 40))

    async def deny_model(*_args, **_kwargs):
        raise AssertionError("model calls forbidden")

    project = _project().model_copy(update={"repository": "fixture-lab/public-collector", "description": None})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com") as client:
        result = await profiles.collect_official_project_profile(
            project,
            "saved-source",
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
    assert "公开网站信息" in result.profile.identitySummaryZh
    assert result.profile.positioningZh and "浏览器上下文" in result.profile.positioningZh
    assert all("商业版功能" not in item.detail for item in result.profile.capabilities)
    assert result.translation_calls == 0


@pytest_asyncio.fixture
async def saved_material(tmp_path):
    def handler(request):
        if request.url.path.endswith("/contents"):
            return httpx.Response(200, json=[{"path": "README.md", "type": "file"}])
        return httpx.Response(200, json=_readme_payload(MARKDOWN, sha="d" * 40))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com") as client:
        return await profiles.collect_official_project_profile(
            _project(),
            "saved-source",
            tmp_path,
            client=client,
            translate=False,
            allow_model_generation=False,
            model_route_identity="a" * 64,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("keep_native", [False, True])
async def test_saved_wrong_role_projection_preserves_source_and_uses_exact_existing_evidence(
    saved_material, keep_native
):
    from app.integrations.rardar.serving_schemas import OfficialProjectProfile
    from app.services.rardar_trending import apply_reading_semantics, project_material

    evidence = saved_material.evidence
    payload = saved_material.profile.model_dump(mode="json")
    # The raw saved section is retained; both bad selections are real prose
    # but have the wrong source role. This is not malformed JSON/hash repair.
    ad = next(x for x in evidence.selectedSections[0].excerpts if "立即免费试用" in x)
    disclaimer = next(x for x in evidence.selectedSections[0].excerpts if "免责声明" in x)
    payload.update(
        identitySummaryZh=ad,
        officialSummaryZh=ad,
        officialTaglineZh=ad,
        officialTaglineEvidenceRefs=["readme:section:1"],
        positioningZh=disclaimer,
        officialPositioningZh=disclaimer,
        positioningEvidenceRefs=["readme:section:1"],
        officialPositioningEvidenceRefs=["readme:section:1"],
        positioningIncludedRoles=["primary_outcome"],
        positioningSourceMode="official_zh",
        officialNarrativeMode="rardar_derived",
    )
    payload["claimEvidenceRefs"].update({ad: ["readme:section:1"], disclaimer: ["readme:section:1"]})
    pro_feature = evidence.selectedSections[2].listItems[0]
    payload["capabilities"] = [
        {
            "title": "断点恢复",
            "detail": pro_feature,
            "sourceMode": "rardar_derived",
            "evidenceRefs": ["readme:section:3:item:1"],
        }
    ]
    payload["capabilityBulletsZh"] = [pro_feature]
    payload["claimEvidenceRefs"][pro_feature] = ["readme:section:3:item:1"]
    ordinary = evidence.selectedSections[1].listItems[1]
    payload["keyDifferentiators"] = [
        {
            "title": "本地输出",
            "detail": ordinary,
            "sourceMode": "rardar_derived",
            "evidenceRefs": ["readme:section:2:item:2"],
        },
        {
            "title": "断点恢复",
            "detail": pro_feature,
            "sourceMode": "rardar_derived",
            "evidenceRefs": ["readme:section:3:item:1"],
        },
    ]
    payload["claimEvidenceRefs"][ordinary] = ["readme:section:2:item:2"]
    payload["rardarDifferentiators"] = payload["keyDifferentiators"]
    if keep_native:
        payload["capabilities"].append(payload["keyDifferentiators"][0])
        payload["capabilityBulletsZh"].append(ordinary)
    profile = OfficialProjectProfile.model_validate_json(json.dumps(payload), strict=True)
    before = profile.model_dump(mode="json"), evidence.model_dump(mode="json")
    original = project_material(profile, evidence)
    projected = apply_reading_semantics(profile, evidence, original)
    assert projected["profile"]["summary"] == "一个通过浏览器采集多个公开网站信息的数据工具，支持保存登录状态。"
    assert "浏览器上下文" in projected["profile"]["positioning"]
    assert projected["materialState"] == ("complete" if keep_native else "partial")
    assert projected["profile"]["capabilities"] == ([ordinary] if keep_native else [])
    if keep_native:
        assert projected["displayProfile"]["keyDifferentiators"] == []
    assert projected["profile"]["generatedAt"] == original["profile"]["generatedAt"]
    assert projected["material"]["sourceRevision"] == evidence.digest
    assert before == (profile.model_dump(mode="json"), evidence.model_dump(mode="json"))
    assert apply_reading_semantics(profile, evidence, projected) == projected


@pytest.mark.asyncio
async def test_saved_introduction_uses_real_overview_not_ad_and_preserves_dates(saved_material):
    from app.integrations.rardar.project_introductions import material

    evidence = saved_material.evidence
    value = {
        "schemaVersion": 1,
        "repository": evidence.repository,
        "githubRepositoryId": evidence.githubRepositoryId,
        "summary": next(x for x in evidence.selectedSections[0].excerpts if "立即免费试用" in x),
        "evidenceRefs": ["readme:section:1"],
        "evidence": evidence.model_dump(mode="json"),
        "sourceMode": "official_zh",
        "sourceLabel": "官方中文资料",
        "savedAt": "2026-10-24T01:02:03+00:00",
        "generatedAt": None,
    }
    before = json.dumps(value, sort_keys=True)
    projected = material(value)
    assert "公开网站信息" in projected["profile"]["summary"]
    assert projected["profile"]["evidenceRefs"] == ["readme:section:2"]
    assert projected["profile"]["generatedAt"] is None
    assert projected["profile"]["savedAt"] == value["savedAt"]
    assert json.dumps(value, sort_keys=True) == before


def test_advertisement_only_description_has_no_project_identity():
    assert profiles._source_claims([], "Sponsored: OtherService. Start your free trial now.")[0] is None


@pytest.mark.asyncio
async def test_unusable_saved_introduction_is_omitted_without_breaking_other_materials(
    saved_material, tmp_path, monkeypatch
):
    from app.integrations.rardar import project_introductions
    from app.services import rardar_trending

    ad = "OtherService 提供自动采集服务，立即免费试用。"
    evidence = saved_material.evidence.model_copy(update={"selectedSections": [], "evidenceIndex": {"description": ad}})
    evidence = evidence.model_copy(
        update={"digest": profiles._digest(evidence.model_dump(mode="json", exclude={"digest"}))}
    )
    value = {
        "schemaVersion": 1,
        "repository": evidence.repository,
        "githubRepositoryId": evidence.githubRepositoryId,
        "summary": ad,
        "evidenceRefs": ["description"],
        "evidence": evidence.model_dump(mode="json"),
        "sourceMode": "official_zh",
        "sourceLabel": "官方中文资料",
        "savedAt": "2026-10-24T01:02:03+00:00",
        "generatedAt": None,
    }
    with pytest.raises(ValueError, match="reading_primary_source_unavailable"):
        project_introductions.material(value)
    monkeypatch.setattr(project_introductions, "saved", lambda _root: {evidence.repository: value})
    assert rardar_trending._read_saved_materials(tmp_path) == {}
