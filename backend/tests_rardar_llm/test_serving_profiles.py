from __future__ import annotations

import base64
from pathlib import Path

import httpx
import pytest

from app.integrations.rardar.adapter import RardarIntelligenceAdapter
from app.integrations.rardar.serving_profiles import (
    EvidenceClaim,
    ProfileTranslation,
    _github_file_url,
    _parse_readme,
    _preferred_chinese_readme,
    _source_language,
    build_official_profiles,
    collect_official_project_profile,
)

FIXTURE = Path(__file__).parents[1] / "tests" / "fixtures" / "rardar_intelligence" / "revision-a"


def _project():
    return RardarIntelligenceAdapter.from_config(str(FIXTURE.resolve())).load_explosion_board().exactRanked[0]


def _readme_payload(markdown: str, *, path: str = "README.md", sha: str = "a" * 40) -> dict:
    return {
        "path": path,
        "sha": sha,
        "encoding": "base64",
        "content": base64.b64encode(markdown.encode()).decode(),
    }


def test_section_aware_parser_skips_badges_and_preserves_feature_lists() -> None:
    markdown = """
# Fixture
[![build](badge.svg)](actions)

An official automation toolkit for developers and operators.

## Table of Contents
- Overview
- Sponsors

## Features
- Generate standalone interactive HTML diagrams from source repositories.
- Compare architecture snapshots over time.
- Trace every diagram node back to a repository path.

## Quick Start
Install the package and run `fixture scan ./repository`.

## Sponsors
Thanks to our sponsors.
"""
    sections = _parse_readme(markdown, "README.md")

    assert sections[0].purpose == "overview"
    features = next(section for section in sections if section.purpose == "capabilities")
    assert len(features.listItems) == 3
    assert "interactive HTML" in features.listItems[0]
    assert all(section.heading != "Sponsors" for section in sections)
    assert any(section.purpose == "quick_start" for section in sections)


def test_parser_ignores_language_navigation_warning_and_sponsor_sections() -> None:
    markdown = """
Read this in other languages
🇺🇸 English | 🇨🇳 简体中文 | 🇯🇵 日本語
> New issues and PRs from new contributors are auto-closed by default.
# Pi Agent Harness
This project provides an extensible coding-agent runtime and interactive CLI.
- Agent runtime with tool calling and state management.
- Unified multi-provider model API.
## ❤️ Sponsors
Thanks to a commercial sponsor.
"""

    sections = _parse_readme(markdown, "README.md")

    assert sections[0].heading == "Pi Agent Harness"
    assert sections[0].purpose == "overview"
    assert sections[0].listItems == [
        "Agent runtime with tool calling and state management.",
        "Unified multi-provider model API.",
    ]
    assert all("Sponsor" not in section.heading for section in sections)
    assert _source_language(markdown, None) == "en"


def test_chinese_readme_selection_is_deterministic() -> None:
    tree = [
        {"path": "README.md", "type": "file"},
        {"path": "README_zh-CN.md", "type": "file"},
        {"path": "README.zh.md", "type": "file"},
    ]

    assert _preferred_chinese_readme(tree) == "README.zh.md"


def test_repository_links_encode_files_use_tree_routes_and_reject_traversal() -> None:
    project = _project()

    assert "/blob/" in _github_file_url(project, "docs/Getting Started.md")
    assert "Getting%20Started.md" in _github_file_url(project, "docs/Getting Started.md")
    assert "/tree/" in _github_file_url(project, "src", kind="dir")
    with pytest.raises(ValueError, match="unsafe repository path"):
        _github_file_url(project, "../outside")


@pytest.mark.asyncio
async def test_blob_sha_and_etag_cache_prevent_duplicate_translation(tmp_path: Path) -> None:
    project = _project()
    requests: list[httpx.Request] = []
    markdown = """
# Fixture
An official developer automation toolkit.
## Features
- Builds evidence-backed project reports.
- Exports a standalone HTML artifact.
"""

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/contents"):
            return httpx.Response(200, json=[{"path": "README.md", "type": "file"}, {"path": "src", "type": "dir"}])
        if request.headers.get("if-none-match") == '"readme-etag"':
            return httpx.Response(304)
        return httpx.Response(200, json=_readme_payload(markdown), headers={"etag": '"readme-etag"'})

    translation_calls = 0

    async def translate(payload):
        nonlocal translation_calls
        translation_calls += 1
        assert "readme:section:1" in payload["evidenceIndex"]
        return ProfileTranslation(
            summary=EvidenceClaim(text="一个面向开发者的官方自动化工具包。", evidenceRefs=["readme:section:1"]),
            capabilities=[
                EvidenceClaim(text="生成有证据支撑的项目报告。", evidenceRefs=["readme:section:2:item:1"]),
                EvidenceClaim(text="导出独立 HTML 交付物。", evidenceRefs=["readme:section:2:item:2"]),
            ],
            useCases=[],
            deliveryForms=[],
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com") as client:
        first = await collect_official_project_profile(
            project,
            "fixture-explosion-a",
            tmp_path,
            client=client,
            translate=True,
            translator=translate,
        )
        second = await collect_official_project_profile(
            project,
            "fixture-explosion-a",
            tmp_path,
            client=client,
            translate=True,
            translator=translate,
        )

    assert first.profile.sourceLabel == "官方 README（译）"
    assert first.profile.capabilityBulletsZh == ["生成有证据支撑的项目报告。", "导出独立 HTML 交付物。"]
    assert second.readme_cache_hit is True
    assert second.translation_cache_hit is True
    assert second.profile == first.profile
    assert translation_calls == 1
    assert sum(request.url.path.endswith("/contents") for request in requests) == 1
    assert len(requests) == 3


@pytest.mark.asyncio
async def test_github_and_llm_failure_degrade_to_a_source_labeled_profile(tmp_path: Path) -> None:
    project = _project()

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429)

    async def unavailable(_payload):
        raise RuntimeError("provider unavailable")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com") as client:
        collected = await collect_official_project_profile(
            project,
            "fixture-explosion-a",
            tmp_path,
            client=client,
            translate=True,
            translator=unavailable,
        )

    assert collected.profile.profileState == "partial"
    assert collected.profile.sourceLabel == "GitHub Description"
    assert collected.profile.translationState == "unavailable"
    assert collected.profile.officialSummaryZh.startswith("官方原文：")
    assert collected.evidence.evidenceIndex["description"] == project.description


@pytest.mark.asyncio
async def test_one_repository_failure_does_not_block_the_profile_batch(tmp_path: Path) -> None:
    board = RardarIntelligenceAdapter.from_config(str(FIXTURE.resolve())).load_explosion_board()
    projects = board.exactRanked[:2]

    async def handler(request: httpx.Request) -> httpx.Response:
        if projects[0].repository in request.url.path:
            return httpx.Response(503)
        if request.url.path.endswith("/contents"):
            return httpx.Response(200, json=[{"path": "README_ZH.md", "type": "file"}])
        return httpx.Response(
            200,
            json=_readme_payload(
                "# 项目简介\n\n这是一个提供真实官方能力说明的开发工具。\n\n## 功能\n\n- 提供可组合模块。",
                path="README_ZH.md",
                sha="b" * 40,
            ),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com") as client:
        result = await build_official_profiles(
            projects,
            "fixture-explosion-a",
            tmp_path,
            client=client,
            translate_top=0,
            concurrency=2,
        )

    assert set(result.profiles) == {project.githubRepositoryId for project in projects}
    assert result.profiles[projects[0].githubRepositoryId].profile.profileState == "partial"
    assert result.profiles[projects[1].githubRepositoryId].profile.sourceLabel == "官方中文 README"


@pytest.mark.asyncio
async def test_paragraph_only_claims_keep_real_readme_evidence_refs(tmp_path: Path) -> None:
    project = _project().model_copy(update={"description": None})
    markdown = """
# 项目简介
这是一个从官方资料生成结构化项目报告并保留证据来源与可验证引用路径的开发工具。
## 功能
它可以保留完整证据路径并导出能够独立浏览和交互查看的 HTML 项目报告。
## 使用场景
适合团队持续审阅大型代码仓库的架构变化、关键模块和实现来源。
"""

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/contents"):
            return httpx.Response(200, json=[{"path": "README.zh.md", "type": "file"}])
        return httpx.Response(200, json=_readme_payload(markdown, path="README.zh.md", sha="c" * 40))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com") as client:
        collected = await collect_official_project_profile(
            project,
            "fixture-explosion-a",
            tmp_path,
            client=client,
            translate=False,
        )

    allowed = set(collected.evidence.evidenceIndex)
    assert collected.profile.capabilityBulletsZh
    assert collected.profile.primaryUseCasesZh
    assert all(
        reference in allowed for references in collected.profile.claimEvidenceRefs.values() for reference in references
    )


@pytest.mark.asyncio
async def test_overview_feature_list_becomes_evidence_backed_capabilities(tmp_path: Path) -> None:
    project = _project().model_copy(update={"description": None})
    markdown = """
# 架构地图工具
它把复杂代码仓库和系统描述转换为可验证、可交互并且能够独立交付给团队审阅的架构地图。
- 根据代码仓库生成交互式 HTML 和 SVG 架构图。
- 对比两份架构快照并突出变化。
- 将节点追踪到对应的仓库路径和证据。
"""

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/contents"):
            return httpx.Response(200, json=[{"path": "README_ZH.md", "type": "file"}])
        return httpx.Response(200, json=_readme_payload(markdown, path="README_ZH.md", sha="d" * 40))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com") as client:
        collected = await collect_official_project_profile(
            project,
            "fixture-explosion-a",
            tmp_path,
            client=client,
            translate=False,
        )

    assert len(collected.profile.capabilityBulletsZh) == 3
    assert "交互式 HTML 和 SVG" in collected.profile.capabilityBulletsZh[0]
    assert all(
        reference in collected.evidence.evidenceIndex
        for capability in collected.profile.capabilityBulletsZh
        for reference in collected.profile.claimEvidenceRefs[capability]
    )
