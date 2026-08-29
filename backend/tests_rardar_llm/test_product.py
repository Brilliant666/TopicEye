from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.integrations.rardar import RardarArtifactError
from app.schemas.rardar_product import (
    FindProjectComparison,
    FindProjectRequest,
    ProjectExplanation,
    ProjectExplanationRequest,
)
from app.services import rardar_product
from app.services.rardar_intelligence import load_explosion_board
from app.services.rardar_llm_control import RardarLLMError
from app.services.rardar_project_evidence import ProjectEvidence


def _settings(*, demo: bool = True, environment: str = "development") -> Settings:
    return Settings(
        DATABASE_URL="postgresql+asyncpg://test:test@127.0.0.1:5432/test",
        APP_ENV=environment,
        RARDAR_PRODUCT_MODE=True,
        RARDAR_DATA_MODE="demo" if demo else "real",
        RARDAR_DEMO_DATA_ENABLED=demo,
        RARDAR_INTELLIGENCE_DATA_DIR="",
    )


def _metadata(*, cached: bool = False):
    return SimpleNamespace(
        model_display_name="configured-rardar-model",
        provider="configured-provider",
        cache_hit=cached,
    )


def _evidence(*, cached: bool = False) -> ProjectEvidence:
    return ProjectEvidence(
        payload={
            "repository": "fixture/repository",
            "description": "An official developer automation toolkit.",
            "readme": {"introduction": "Official introduction", "headings": []},
            "topLevelTree": [{"path": "src", "type": "dir"}, {"path": "pyproject.toml", "type": "file"}],
            "packageManifests": ["pyproject.toml"],
            "metadata": {"licenseSpdxId": "MIT"},
            "latestRelease": None,
            "evidenceIndex": {
                "description": "An official developer automation toolkit.",
                "readme:introduction": "Official introduction",
                "tree:src": "dir: src",
                "file:pyproject.toml": "file: pyproject.toml",
                "license": "MIT",
            },
            "collectionLimits": {"githubRequests": 4},
            "officialProfile": {
                "officialSummaryZh": "An official developer automation toolkit.",
                "capabilities": [
                    {
                        "title": "可组合自动化",
                        "detail": "提供可组合的自动化能力。",
                        "shortDetail": "组合自动化模块",
                        "evidenceRefs": ["readme:introduction"],
                    }
                ],
                "capabilityBulletsZh": ["提供可组合的自动化能力。"],
                "productFormsZh": ["开发工具"],
                "deliveryFormsZh": ["Python 模块"],
            },
        },
        digest="a" * 64,
        allowed_refs=frozenset({"description", "readme:introduction", "tree:src", "file:pyproject.toml", "license"}),
        path_refs={"tree:src": "src", "file:pyproject.toml": "pyproject.toml"},
        official_intro={
            "text": "An official developer automation toolkit.",
            "sourceLabel": "官方介绍",
            "evidenceRefs": ["description"],
        },
        expected_intro_label="官方介绍（译）",
        cache_hit=cached,
    )


def _insight() -> ProjectExplanation:
    return ProjectExplanation.model_validate_json(
        json.dumps(
            {
                "conclusionSummary": {
                    "text": "它把可组合的自动化能力封装成可复用模块，适合作为开发工作流的基础组件。",
                    "evidenceRefs": ["description", "readme:introduction"],
                },
                "differentiators": [
                    {
                        "text": "相比一次性脚本，可组合模块更适合作为可扩展工作流的基础。",
                        "evidenceRefs": ["readme:introduction", "tree:src"],
                    }
                ],
                "reusableAssets": [
                    {
                        "reuseType": "module_library",
                        "asset": "src 模块",
                        "howToUse": "从 src 目录提取可组合能力并做接口适配。",
                        "evidenceRefs": ["tree:src"],
                    }
                ],
                "reuseCost": {
                    "level": "medium",
                    "reason": "需要按 pyproject.toml 安装依赖并适配 src 模块接口。",
                    "evidenceRefs": ["file:pyproject.toml", "tree:src"],
                },
                "bestFitScenarios": [
                    {"text": "需要组合自动化模块的开发团队。", "evidenceRefs": ["description", "tree:src"]}
                ],
                "startHere": [
                    {"label": "先查看项目依赖入口", "path": "pyproject.toml", "evidenceRefs": ["file:pyproject.toml"]}
                ],
                "implementationBoundaries": [{"text": "采用 MIT 许可证。", "evidenceRefs": ["license"]}],
            },
            ensure_ascii=False,
        ),
        strict=True,
    )


def test_demo_board_is_explicit_and_never_used_in_production() -> None:
    board = load_explosion_board(_settings())
    assert board.dataMode == "demo"
    assert board.dataLabel == "本地演示数据 · explosion-board-demo-v1"
    assert len(board.exactRanked) == 5
    assert len(board.pendingRanked) == 3

    with pytest.raises(RardarArtifactError):
        load_explosion_board(_settings(environment="production"))

    real = _settings(demo=False)
    real.RARDAR_DEMO_DATA_ENABLED = True
    not_synced = load_explosion_board(real)
    assert not_synced.state == "not_synced"
    assert not_synced.dataMode == "real"


def test_demo_board_never_masks_a_damaged_configured_generation(tmp_path) -> None:
    (tmp_path / "serving").mkdir()
    (tmp_path / "serving" / "current.json").write_text("{broken", encoding="utf-8")
    config = _settings(demo=False)
    config.RARDAR_INTELLIGENCE_DATA_DIR = str(tmp_path)

    with pytest.raises(RardarArtifactError, match="strict validation") as caught:
        load_explosion_board(config)

    assert caught.value.code == "rardar_serving_pointer_invalid"


@pytest.mark.asyncio
async def test_project_explanation_binds_prompt_and_cache_to_facts(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    async def structured(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(value=_insight(), metadata=_metadata(cached=True))

    monkeypatch.setattr(rardar_product, "call_rardar_structured", structured)
    monkeypatch.setattr(rardar_product, "collect_project_evidence", lambda *_args, **_kwargs: _async(_evidence()))
    response = await rardar_product.explain_project(
        ProjectExplanationRequest(
            repository="openai/openai-agents-python",
            generationId="local-demo-explosion-v1",
        ),
        _settings(),
    )

    assert response.state == "ready"
    assert response.cacheHit is True
    assert calls[0]["reasoning_effort"] is None
    assert calls[0]["prompt_version"] == "rardar-project-insight-v5"
    assert "evidenceDigest=" in calls[0]["messages"][1]["content"]
    assert "schemaVersion=rardar-project-insight-schema-v5" in calls[0]["messages"][1]["content"]
    assert "local-demo-explosion-v1" not in calls[0]["messages"][1]["content"]
    assert "observedStarDelta" not in calls[0]["messages"][1]["content"]
    assert response.analysis and response.analysis.startHere[0].path == "pyproject.toml"


@pytest.mark.asyncio
async def test_stable_project_insight_uses_saved_static_evidence_without_github(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []

    async def structured(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(value=_insight(), metadata=_metadata(cached=True))

    async def forbidden_github(*_args, **_kwargs):
        raise AssertionError("detail insight must not call GitHub")

    detail = SimpleNamespace(project=SimpleNamespace(repository="fixture/repository"))
    monkeypatch.setattr(rardar_product, "load_project_detail", lambda *_args: (detail, '"etag"'))
    monkeypatch.setattr(rardar_product, "_static_project_evidence", lambda _detail: _evidence(cached=True))
    monkeypatch.setattr(rardar_product, "collect_project_evidence", forbidden_github)
    monkeypatch.setattr(rardar_product, "call_rardar_structured", structured)

    response = await rardar_product.explain_project_by_id(1211139949, "generation-v2", _settings())

    assert response.state == "ready"
    assert response.githubRepositoryId == 1211139949
    assert response.evidenceCacheHit is True
    assert calls and "projectEvidence=" in calls[0]["messages"][1]["content"]


async def _async(value):
    return value


@pytest.mark.asyncio
async def test_project_explanation_unavailable_keeps_official_intro_and_facts(monkeypatch: pytest.MonkeyPatch) -> None:
    async def rejected(**_kwargs):
        raise RardarLLMError("rardar_llm_invalid_output")

    monkeypatch.setattr(rardar_product, "call_rardar_structured", rejected)
    monkeypatch.setattr(rardar_product, "call_rardar_llm", rejected)
    monkeypatch.setattr(rardar_product, "collect_project_evidence", lambda *_args, **_kwargs: _async(_evidence()))
    request = ProjectExplanationRequest(repository="browser-use/browser-use", generationId="local-demo-explosion-v1")
    response = await rardar_product.explain_project(request, _settings())
    assert response.state == "unavailable"
    assert response.errorCode == "rardar_llm_invalid_output"
    assert response.officialIntro.text == "An official developer automation toolkit."
    assert len(load_explosion_board(_settings()).exactRanked) == 5


@pytest.mark.asyncio
async def test_project_explanation_accepts_locally_validated_json_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def rejected(**_kwargs):
        raise RardarLLMError("rardar_llm_invalid_output")

    async def json_response(**_kwargs):
        return SimpleNamespace(content=_insight().model_dump_json(), metadata=_metadata())

    monkeypatch.setattr(rardar_product, "call_rardar_structured", rejected)
    monkeypatch.setattr(rardar_product, "call_rardar_llm", json_response)
    monkeypatch.setattr(rardar_product, "collect_project_evidence", lambda *_args, **_kwargs: _async(_evidence()))
    response = await rardar_product.explain_project(
        ProjectExplanationRequest(
            repository="browser-use/browser-use",
            generationId="local-demo-explosion-v1",
        ),
        _settings(),
    )

    assert response.state == "ready"
    assert response.format == "structured"
    assert response.analysis is not None
    assert response.analysis.reusableAssets[0].asset == "src 模块"


@pytest.mark.asyncio
async def test_project_explanation_rejects_rank_repetition_and_generic_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid = _insight().model_copy(deep=True)
    invalid.differentiators[0].text = "排名第 1，Star 增长很快。"
    invalid.implementationBoundaries[0].text = "稳定性需要验证"

    async def structured(**_kwargs):
        return SimpleNamespace(value=invalid, metadata=_metadata())

    async def rejected(**_kwargs):
        raise RardarLLMError("rardar_llm_invalid_output")

    monkeypatch.setattr(rardar_product, "call_rardar_structured", structured)
    monkeypatch.setattr(rardar_product, "call_rardar_llm", rejected)
    monkeypatch.setattr(rardar_product, "collect_project_evidence", lambda *_args, **_kwargs: _async(_evidence()))
    response = await rardar_product.explain_project(
        ProjectExplanationRequest(repository="browser-use/browser-use", generationId="local-demo-explosion-v1"),
        _settings(),
    )
    assert response.state == "unavailable"
    assert response.analysis is None


@pytest.mark.parametrize(
    ("case", "expected_code"),
    [
        ("unknown_ref", "rardar_llm_invalid_evidence_ref"),
        ("invented_path", "rardar_llm_invalid_start_here"),
        ("generic_boundary", "rardar_llm_generic_boundary"),
    ],
)
def test_project_insight_validation_fails_closed(case: str, expected_code: str) -> None:
    insight = _insight().model_copy(deep=True)
    if case == "unknown_ref":
        insight.differentiators[0].evidenceRefs = ["tree:not-present"]
    elif case == "invented_path":
        insight.startHere[0].path = "README.md#invented"
    else:
        insight.implementationBoundaries[0].text = "兼容性尚需进一步验证"

    with pytest.raises(RardarLLMError) as error:
        rardar_product._validate_project_insight(insight, _evidence())

    assert error.value.code == expected_code


def test_project_insight_v4_requires_a_bounded_reuse_cost_and_rejects_personalized_context() -> None:
    payload = _insight().model_dump(mode="json")
    payload["reuseCost"]["level"] = "free"
    with pytest.raises(ValidationError):
        ProjectExplanation.model_validate(payload, strict=True)

    personalized = _insight().model_copy(deep=True)
    personalized.bestFitScenarios[0].text = "适合你的 Rardar 项目直接集成。"
    with pytest.raises(RardarLLMError) as error:
        rardar_product._validate_project_insight(personalized, _evidence())
    assert error.value.code == "rardar_llm_personalized_context"


def test_project_insight_v4_rejects_a_duplicated_official_definition() -> None:
    duplicated = _insight().model_copy(deep=True)
    duplicated.conclusionSummary.text = "An official developer automation toolkit."

    with pytest.raises(RardarLLMError) as error:
        rardar_product._validate_project_insight(duplicated, _evidence())

    assert error.value.code == "rardar_llm_repeated_official_intro"


@pytest.mark.parametrize(
    "repeated",
    [
        "提供可组合的自动化能力。",
        "提供灵活且可组合的自动化能力。",
        "核心亮点：提供 可组合 的自动化能力",
        "核心亮点：提供　可组合的自动化能力。",
    ],
)
def test_project_insight_hides_differentiators_that_repeat_official_capabilities(repeated: str) -> None:
    insight = _insight().model_copy(deep=True)
    insight.differentiators[0].text = repeated

    validated = rardar_product._validate_project_insight(insight, _evidence())

    assert validated.differentiators == []
    assert validated.reusableAssets
    assert validated.reuseCost


def test_project_insight_keeps_evidence_backed_comparative_judgment() -> None:
    insight = _insight()

    validated = rardar_product._validate_project_insight(insight, _evidence())

    assert len(validated.differentiators) == 1
    assert "相比一次性脚本" in validated.differentiators[0].text


def test_project_insight_overlap_normalizes_case_whitespace_and_punctuation() -> None:
    overlaps, exactish = rardar_product._high_text_overlap(
        "核心亮点： Architecture   Delta",
        "architecture-delta",
    )

    assert overlaps is True
    assert exactish is True


def _github_item(index: int) -> dict:
    repository = f"fixture-owner/project-{index}"
    return {
        "id": 1000 + index,
        "full_name": repository,
        "html_url": f"https://github.com/{repository}",
        "description": f"Project {index}",
        "stargazers_count": 1000 - index,
        "updated_at": "2026-08-27T00:00:00Z",
        "language": "Python",
        "license": {"spdx_id": "MIT"},
        "topics": ["automation", "video"],
    }


@pytest.mark.asyncio
async def test_find_project_returns_live_five_and_compares_exact_top_three(monkeypatch: pytest.MonkeyPatch) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/search/repositories":
            return httpx.Response(200, json={"items": [_github_item(index) for index in range(1, 7)]})
        return httpx.Response(404)

    async def structured(**kwargs):
        repositories = [f"fixture-owner/project-{index}" for index in range(1, 4)]
        value = FindProjectComparison.model_validate_json(
            json.dumps(
                {
                    "candidates": [
                        {
                            "repository": repository,
                            "whatItDoes": "提供开发工具能力。",
                            "whyMatched": "仓库元数据与需求关键词匹配。",
                            "reusableParts": ["核心模块"],
                            "integrationCost": "medium",
                            "risks": ["需要静态检查"],
                            "recommendation": "先做最小验证。",
                            "reuseType": "module_library",
                        }
                        for repository in repositories
                    ],
                    "overallConclusion": "优先验证前三个真实候选。",
                }
            ),
            strict=True,
        )
        assert kwargs["reasoning_effort"] is None
        return SimpleNamespace(value=value, metadata=_metadata())

    monkeypatch.setattr(rardar_product, "call_rardar_structured", structured)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com") as client:
        response = await rardar_product.find_projects(
            FindProjectRequest(requirement="我需要一个 Python 视频自动化项目"),
            _settings(demo=False),
            client=client,
        )

    assert response.searchState == "github_live"
    assert len(response.quickCandidates) == 6
    assert response.aiState == "ready"
    assert {item.repository for item in response.comparison.candidates} == {
        item.repository for item in response.quickCandidates[:3]
    }
    assert all(item.dataState == "github_live" for item in response.quickCandidates)


@pytest.mark.asyncio
async def test_find_project_github_failure_uses_labeled_demo_and_keeps_ai_optional(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "rate limited"})

    async def rejected(**_kwargs):
        raise RardarLLMError("rardar_llm_not_configured")

    monkeypatch.setattr(rardar_product, "call_rardar_structured", rejected)
    monkeypatch.setattr(rardar_product, "call_rardar_llm", rejected)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com") as client:
        response = await rardar_product.find_projects(
            FindProjectRequest(requirement="我想获取抖音主页作品并下载视频"),
            _settings(),
            client=client,
        )

    assert response.searchState == "demo"
    assert len(response.quickCandidates) >= 5
    assert all(item.dataState == "local_demo" for item in response.quickCandidates)
    assert response.aiState == "unavailable"
    assert "本地演示" in response.coverageLabel


@pytest.mark.asyncio
async def test_find_project_accepts_locally_validated_json_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/search/repositories":
            return httpx.Response(200, json={"items": [_github_item(index) for index in range(1, 7)]})
        return httpx.Response(404)

    async def rejected(**_kwargs):
        raise RardarLLMError("rardar_llm_invalid_output")

    async def json_response(**_kwargs):
        return SimpleNamespace(
            content=json.dumps(
                {
                    "candidates": [
                        {
                            "repository": f"fixture-owner/project-{index}",
                            "whatItDoes": "提供视频自动化能力。",
                            "whyMatched": "仓库事实匹配需求关键词。",
                            "reusableParts": ["下载模块"],
                            "integrationCost": "medium",
                            "risks": ["需要静态检查"],
                            "recommendation": "先做最小验证。",
                            "reuseType": "module_library",
                        }
                        for index in range(1, 4)
                    ],
                    "overallConclusion": "优先验证前三个真实候选。",
                },
                ensure_ascii=False,
            ),
            metadata=_metadata(),
        )

    monkeypatch.setattr(rardar_product, "call_rardar_structured", rejected)
    monkeypatch.setattr(rardar_product, "call_rardar_llm", json_response)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com") as client:
        response = await rardar_product.find_projects(
            FindProjectRequest(requirement="我需要一个 Python 视频自动化项目"),
            _settings(demo=False),
            client=client,
        )

    assert response.aiState == "ready"
    assert response.comparison is not None
    assert len(response.comparison.candidates) == 3
    assert {item.reuseType for item in response.comparison.candidates} == {"module_library"}


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/owner/repo",
        "https://github.com/owner/repo/issues",
        "https://evil.example/owner/repo",
        "https://github.com/owner/../repo",
        "https://user:password@github.com/owner/repo",
    ],
)
def test_find_project_rejects_unsafe_or_non_repository_urls(url: str) -> None:
    with pytest.raises(ValidationError):
        FindProjectRequest(requirement="需要一个可复用的项目", repositoryUrl=url)
