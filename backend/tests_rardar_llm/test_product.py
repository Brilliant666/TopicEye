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


def _settings(*, demo: bool = True, environment: str = "development") -> Settings:
    return Settings(
        DATABASE_URL="postgresql+asyncpg://test:test@127.0.0.1:5432/test",
        APP_ENV=environment,
        RARDAR_PRODUCT_MODE=True,
        RARDAR_DEMO_DATA_ENABLED=demo,
        RARDAR_INTELLIGENCE_DATA_DIR="",
    )


def _metadata(*, cached: bool = False):
    return SimpleNamespace(
        model_display_name="configured-rardar-model",
        provider="configured-provider",
        cache_hit=cached,
    )


def test_demo_board_is_explicit_and_never_used_in_production() -> None:
    board = load_explosion_board(_settings())
    assert board.dataMode == "demo"
    assert board.dataLabel == "本地演示数据 · explosion-board-demo-v1"
    assert len(board.exactRanked) == 5
    assert len(board.pendingRanked) == 3

    with pytest.raises(RardarArtifactError):
        load_explosion_board(_settings(environment="production"))


def test_demo_board_never_masks_a_damaged_configured_generation(tmp_path) -> None:
    (tmp_path / "current.json").write_text("{broken", encoding="utf-8")
    config = _settings()
    config.RARDAR_INTELLIGENCE_DATA_DIR = str(tmp_path)

    with pytest.raises(RardarArtifactError, match="current pointer") as caught:
        load_explosion_board(config)

    assert caught.value.code == "rardar_current_pointer_invalid"


@pytest.mark.asyncio
async def test_project_explanation_binds_prompt_and_cache_to_facts(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    async def structured(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            value=ProjectExplanation(
                summaryZh="一个轻量多智能体框架。",
                whyWorthWatching="演示事实显示它在观察窗口内增长较快。",
                reuseIdeas=["复用代理编排模块"],
                risks=["需核对真实版本和许可证"],
            ),
            metadata=_metadata(cached=True),
        )

    monkeypatch.setattr(rardar_product, "call_rardar_structured", structured)
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
    assert calls[0]["prompt_version"] == "rardar-project-explanation-v1"
    assert "local-demo-explosion-v1" in calls[0]["messages"][1]["content"]
    assert "openai/openai-agents-python" in calls[0]["messages"][1]["content"]


@pytest.mark.asyncio
async def test_project_explanation_plain_and_unavailable_do_not_break_facts(monkeypatch: pytest.MonkeyPatch) -> None:
    async def rejected(**_kwargs):
        raise RardarLLMError("rardar_llm_invalid_output")

    async def plain(**_kwargs):
        return SimpleNamespace(content="中文简介：可复用。风险：需验证许可证。", metadata=_metadata())

    monkeypatch.setattr(rardar_product, "call_rardar_structured", rejected)
    monkeypatch.setattr(rardar_product, "call_rardar_llm", plain)
    request = ProjectExplanationRequest(repository="browser-use/browser-use", generationId="local-demo-explosion-v1")
    response = await rardar_product.explain_project(request, _settings())
    assert response.state == "plain"
    assert response.plainText
    assert load_explosion_board(_settings()).exactRanked[1].observedStarDelta == 570

    monkeypatch.setattr(rardar_product, "call_rardar_llm", rejected)
    response = await rardar_product.explain_project(request, _settings())
    assert response.state == "unavailable"
    assert response.errorCode == "rardar_llm_invalid_output"
    assert len(load_explosion_board(_settings()).exactRanked) == 5


@pytest.mark.asyncio
async def test_project_explanation_accepts_locally_validated_json_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def rejected(**_kwargs):
        raise RardarLLMError("rardar_llm_invalid_output")

    async def json_response(**_kwargs):
        return SimpleNamespace(
            content=json.dumps(
                {
                    "summaryZh": "一个可复用的浏览器自动化项目。",
                    "whyWorthWatching": "观察窗口内新增关注较快。",
                    "reuseIdeas": ["复用浏览器控制层"],
                    "risks": ["需要核对许可证和接口稳定性"],
                },
                ensure_ascii=False,
            ),
            metadata=_metadata(),
        )

    monkeypatch.setattr(rardar_product, "call_rardar_structured", rejected)
    monkeypatch.setattr(rardar_product, "call_rardar_llm", json_response)
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
    assert response.analysis.reuseIdeas == ["复用浏览器控制层"]


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
