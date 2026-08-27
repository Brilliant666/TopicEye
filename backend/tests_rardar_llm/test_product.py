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
                "officialIntro": {
                    "text": "一个官方开发者自动化工具包。",
                    "sourceLabel": "官方介绍（译）",
                    "evidenceRefs": ["description"],
                },
                "coreHighlights": [{"text": "提供可组合的自动化能力。", "evidenceRefs": ["readme:introduction"]}],
                "reusableAssets": [
                    {
                        "reuseType": "module_library",
                        "asset": "src 模块",
                        "howToUse": "从 src 目录提取可组合能力并做接口适配。",
                        "evidenceRefs": ["tree:src"],
                    }
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
    (tmp_path / "current.json").write_text("{broken", encoding="utf-8")
    config = _settings(demo=False)
    config.RARDAR_INTELLIGENCE_DATA_DIR = str(tmp_path)

    with pytest.raises(RardarArtifactError, match="current pointer") as caught:
        load_explosion_board(config)

    assert caught.value.code == "rardar_current_pointer_invalid"


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
    assert calls[0]["prompt_version"] == "rardar-project-insight-v2"
    assert "evidenceDigest=" in calls[0]["messages"][1]["content"]
    assert "schemaVersion=rardar-project-insight-schema-v2" in calls[0]["messages"][1]["content"]
    assert "local-demo-explosion-v1" not in calls[0]["messages"][1]["content"]
    assert "observedStarDelta" not in calls[0]["messages"][1]["content"]
    assert response.analysis and response.analysis.startHere[0].path == "pyproject.toml"


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
    invalid.coreHighlights[0].text = "排名第 1，Star 增长很快。"
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
        insight.coreHighlights[0].evidenceRefs = ["tree:not-present"]
    elif case == "invented_path":
        insight.startHere[0].path = "README.md#invented"
    else:
        insight.implementationBoundaries[0].text = "兼容性尚需进一步验证"

    with pytest.raises(RardarLLMError) as error:
        rardar_product._validate_project_insight(insight, _evidence())

    assert error.value.code == expected_code


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
