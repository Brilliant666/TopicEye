from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx
import pytest

from app.integrations.rardar.adapter import RardarIntelligenceAdapter
from app.integrations.rardar.serving_profiles import (
    EvidenceClaim,
    ProfileTranslation,
    ProfileTranslationError,
    _bounded_translation_evidence,
    _github_file_url,
    _parse_readme,
    _preferred_chinese_readme,
    _readme_redirect_target,
    _safe_fallback_identity,
    _source_language,
    _structure_capability,
    _validate_translation,
    build_official_profiles,
    collect_official_project_profile,
)
from app.integrations.rardar.serving_schemas import ServingCapability

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


def test_content_sanitizer_rejects_media_urls_redirects_commands_and_placeholders() -> None:
    markdown = """
# Safe Toolkit
<p align="center"><img src="https://example.test/logo.png" height="200"></p>
https://github.com/user-attachments/assets/deadbeef
This README moved to [the new README](docs/README.zh-CN.md).
npm install unsafe-noise

一个用于验证官方项目内容质量的开发工具，保留真实用途而不展示导航噪声。

## 功能
- 能力说明 1
- 功能说明 2
- 生成带证据引用的中文项目档案。
"""

    sections = _parse_readme(markdown, "README.md")
    rendered = " ".join(
        [
            *(excerpt for section in sections for excerpt in section.excerpts),
            *(item for section in sections for item in section.listItems),
        ]
    )

    assert "项目内容质量" in rendered
    assert "证据引用" in rendered
    assert "user-attachments" not in rendered
    assert "img src" not in rendered
    assert "npm install" not in rendered
    assert "能力说明 1" not in rendered
    assert "功能说明 2" not in rendered


def test_content_sanitizer_keeps_meaningful_text_inside_html_containers() -> None:
    markdown = """
# Safe Toolkit
<p><strong>Safe Toolkit</strong> 把公开仓库证据整理成可验证的中文项目档案。</p>
<script>window.evil = true</script>

## 功能
- <strong>证据绑定</strong>：每个结论都回指真实来源。
"""

    sections = _parse_readme(markdown, "README.md")
    rendered = " ".join(
        [
            *(excerpt for section in sections for excerpt in section.excerpts),
            *(item for section in sections for item in section.listItems),
        ]
    )

    assert "可验证的中文项目档案" in rendered
    assert "每个结论都回指真实来源" in rendered
    assert "window.evil" not in rendered


def test_readme_redirect_target_is_same_repository_and_path_safe() -> None:
    assert (
        _readme_redirect_target(
            "This README moved to [the maintained README](docs/README.zh-CN.md).",
            "README.md",
        )
        == "docs/README.zh-CN.md"
    )
    assert _readme_redirect_target("README moved to https://outside.test/README.md", "README.md") is None
    assert _readme_redirect_target("README moved to [unsafe](../README.md)", "docs/README.md") is None


def test_long_english_fallback_never_becomes_a_long_visible_summary() -> None:
    source = (
        "This project contains a very long navigation-heavy English description intended only to verify "
        "that a failed translation cannot leak a paragraph-sized block of source prose into the Chinese "
        "Today card or project detail page, even when all network and model fallbacks are active."
    )

    summary, issues = _safe_fallback_identity(source)

    assert summary == "官方资料暂不足，当前仅展示可验证的仓库与 Star 事实。"
    assert issues == ["identity_source_rejected"]


@pytest.mark.parametrize(
    "value",
    [
        "Run the following command to install the Codex CLI for your terminal.",
        "You can brew install herdr, or npm install herdr and then run it.",
        "PowerShell: irm https://example.invalid/install.ps1 | iex",
    ],
)
def test_summary_sanitizer_rejects_install_instructions(value: str) -> None:
    summary, issues = _safe_fallback_identity(value)

    assert summary == "官方资料暂不足，当前仅展示可验证的仓库与 Star 事实。"
    assert issues == ["identity_source_rejected"]


def test_translation_evidence_is_bounded_without_inventing_or_renaming_refs() -> None:
    evidence = {
        "repository": "官方 GitHub 仓库身份",
        "description": "A bounded translation fixture",
        **{
            f"readme:section:{section}:item:{item}": f"README evidence {section}-{item} " + ("x" * 180)
            for section in range(1, 13)
            for item in range(1, 9)
        },
        **{f"readme:section:{section}": f"README section {section} " + ("y" * 500) for section in range(1, 13)},
    }

    bounded = _bounded_translation_evidence(evidence)

    assert bounded["repository"] == evidence["repository"]
    assert bounded["description"] == evidence["description"]
    assert set(bounded).issubset(evidence)
    assert len(bounded) <= 16
    assert sum(len(key) + len(value) for key, value in bounded.items()) <= 1800
    assert any(key.endswith(":item:1") for key in bounded)


def test_translation_evidence_orders_readme_sections_numerically_and_bounds_each_excerpt() -> None:
    evidence = {
        "repository": "官方 GitHub 仓库身份",
        "description": "A project description",
        "readme:section:1": "Overview " + ("a" * 700),
        "readme:section:2": "Capabilities " + ("b" * 700),
        "readme:section:10": "Late adapter notes " + ("c" * 700),
    }

    bounded = _bounded_translation_evidence(evidence)

    assert list(bounded).index("readme:section:2") < list(bounded).index("readme:section:10")
    assert all(len(value) <= 480 for value in bounded.values())


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
                ServingCapability(
                    title="证据项目报告",
                    detail="生成有证据支撑的项目报告。",
                    shortDetail="生成有证据支撑的项目报告。",
                    evidenceRefs=["readme:section:2:item:1"],
                ),
                ServingCapability(
                    title="独立 HTML 交付",
                    detail="导出独立 HTML 交付物。",
                    shortDetail="导出独立 HTML 交付物。",
                    evidenceRefs=["readme:section:2:item:2"],
                ),
            ],
            productForms=[],
            supportedEnvironments=[],
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
    assert first.profile.qualityState == "ready"
    assert first.profile.qualityIssues == []
    assert first.profile.coreValueZh is not None
    assert first.profile.coreValueEvidenceRefs
    assert first.profile.capabilityBulletsZh == ["生成有证据支撑的项目报告。", "导出独立 HTML 交付物。"]
    assert [item.title for item in first.profile.capabilities] == ["证据项目报告", "独立 HTML 交付"]
    assert second.readme_cache_hit is True
    assert second.translation_cache_hit is True
    assert second.profile == first.profile
    assert translation_calls == 1
    assert sum(request.url.path.endswith("/contents") for request in requests) == 1
    assert len(requests) == 3


@pytest.mark.asyncio
async def test_same_repository_readme_redirect_is_followed_and_cached_at_the_final_blob(tmp_path: Path) -> None:
    project = _project().model_copy(update={"description": None})
    requested: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        if request.url.path.endswith("/contents"):
            return httpx.Response(200, json=[{"path": "README.md", "type": "file"}])
        if request.url.path.endswith("/readme"):
            return httpx.Response(
                200,
                json=_readme_payload(
                    "# 旧入口\nThis README moved to [the maintained README](docs/README.zh-CN.md).",
                    sha="1" * 40,
                ),
            )
        if request.url.path.endswith("/contents/docs/README.zh-CN.md"):
            return httpx.Response(
                200,
                json=_readme_payload(
                    "# 项目简介\n这是一个提供可追溯项目画像和结构化能力说明的中文官方文档。\n"
                    "## 功能\n- 生成带官方证据引用的项目档案。",
                    path="docs/README.zh-CN.md",
                    sha="2" * 40,
                ),
            )
        raise AssertionError(request.url.path)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com") as client:
        collected = await collect_official_project_profile(
            project,
            "fixture-explosion-a",
            tmp_path,
            client=client,
            translate=False,
        )

    pointer = next((tmp_path / "readmes").rglob("current.json"))
    assert collected.profile.readmePath == "docs/README.zh-CN.md"
    assert collected.profile.readmeBlobSha == "2" * 40
    assert collected.profile.sourceLabel == "官方中文 README"
    assert json.loads(pointer.read_text(encoding="utf-8"))["sha"] == "2" * 40
    assert requested[-1].endswith("/contents/docs/README.zh-CN.md")


@pytest.mark.asyncio
async def test_readme_redirect_following_is_bounded_to_two_hops(tmp_path: Path) -> None:
    project = _project().model_copy(update={"description": "安全的后备项目简介。"})
    requested: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        if request.url.path.endswith("/contents"):
            return httpx.Response(200, json=[{"path": "README.md", "type": "file"}])
        if request.url.path.endswith("/readme"):
            return httpx.Response(
                200,
                json=_readme_payload("README moved to [next](docs/README.one.md).", sha="1" * 40),
            )
        if request.url.path.endswith("/contents/docs/README.one.md"):
            return httpx.Response(
                200,
                json=_readme_payload(
                    "README moved to [next](README.two.md).",
                    path="docs/README.one.md",
                    sha="2" * 40,
                ),
            )
        if request.url.path.endswith("/contents/docs/README.two.md"):
            return httpx.Response(
                200,
                json=_readme_payload(
                    "README moved to [next](README.three.md).",
                    path="docs/README.two.md",
                    sha="3" * 40,
                ),
            )
        if request.url.path.endswith("/contents/docs/README.three.md"):
            raise AssertionError("redirect depth must be bounded")
        raise AssertionError(request.url.path)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com") as client:
        collected = await collect_official_project_profile(
            project,
            "fixture-explosion-a",
            tmp_path,
            client=client,
            translate=False,
        )

    assert collected.profile.readmePath == "docs/README.two.md"
    assert not any(path.endswith("README.three.md") for path in requested)


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
    assert collected.profile.officialSummaryZh.startswith("翻译待补全：")
    assert collected.profile.qualityState == "partial"
    assert collected.evidence.evidenceIndex["description"] == project.description


@pytest.mark.asyncio
async def test_rejected_source_never_exposes_unsafe_semantic_claims(tmp_path: Path) -> None:
    project = _project().model_copy(update={"description": "https://github.com/user-attachments/assets/deadbeef"})

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com") as client:
        collected = await collect_official_project_profile(
            project,
            "fixture-explosion-a",
            tmp_path,
            client=client,
            translate=True,
        )

    assert collected.profile.qualityState == "rejected"
    assert "identity_source_rejected" in collected.profile.qualityIssues
    assert collected.profile.coreValueZh is None
    assert collected.profile.keyDifferentiators == []
    assert collected.profile.capabilities == []
    assert "user-attachments" not in collected.profile.identitySummaryZh


def test_translation_rejects_duplicate_or_unbound_core_value() -> None:
    summary = EvidenceClaim(text="一个保留官方证据的项目画像工具。", evidenceRefs=["readme:section:1"])
    capability = ServingCapability(
        title="证据绑定",
        detail="把每项能力绑定到可核验的官方章节。",
        evidenceRefs=["readme:section:2"],
    )
    common = {
        "summary": summary,
        "keyDifferentiators": [capability],
        "capabilities": [capability],
        "productForms": [],
        "supportedEnvironments": [],
        "useCases": [],
        "deliveryForms": [],
    }

    with pytest.raises(ProfileTranslationError, match="rardar_profile_translation_invalid"):
        _validate_translation(
            ProfileTranslation(coreValue=summary, **common),
            {"readme:section:1", "readme:section:2"},
        )
    with pytest.raises(ProfileTranslationError, match="rardar_profile_translation_invalid"):
        _validate_translation(
            ProfileTranslation(
                coreValue=EvidenceClaim(text="通过版本化证据降低采用判断的不确定性。", evidenceRefs=["invented"]),
                **common,
            ),
            {"readme:section:1", "readme:section:2"},
        )


def test_profile_builder_contains_no_repository_specific_content_branch() -> None:
    source = Path(__file__).parents[1] / "app" / "integrations" / "rardar" / "serving_profiles.py"
    lowered = source.read_text(encoding="utf-8").casefold()
    assert "tt-a1i" not in lowered
    assert "archify" not in lowered


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


@pytest.mark.asyncio
async def test_structured_product_identity_is_derived_from_evidence_without_repository_special_cases(
    tmp_path: Path,
) -> None:
    project = _project().model_copy(update={"repository": "fixture-lab/diagram-tool", "description": None})
    markdown = """
# Diagram Tool
An Agent Skill that turns source repositories into interactive technical diagrams.

It uses a Node.js rendering and validation system in Raven, Cursor, Claude Code, Codex CLI, OpenCode, and a browser.

## Features
- Produces architecture, workflow, sequence, data-flow, and lifecycle diagrams.
- Compares Before, Delta, and After architecture snapshots.
- Uses a Typed JSON IR with deterministic validation.
- Exports standalone HTML, PNG, SVG, and WebM artifacts.

## Installation
Install the Node.js package and read archify/SKILL.md before running the CLI.

## How It Works
This is not a WYSIWYG drawing editor or a Mermaid theme. Diagram reachability is not runtime impact.

## Examples
Open examples/ for complete outputs.
"""

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/contents"):
            return httpx.Response(
                200,
                json=[
                    {"path": "README.md", "type": "file"},
                    {"path": "archify", "type": "dir"},
                    {"path": "examples", "type": "dir"},
                    {"path": "package.json", "type": "file"},
                ],
            )
        return httpx.Response(200, json=_readme_payload(markdown, sha="e" * 40))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com") as client:
        collected = await collect_official_project_profile(
            project,
            "fixture-explosion-a",
            tmp_path,
            client=client,
            translate=False,
        )

    profile = collected.profile
    assert profile.profileSchemaVersion == "rardar-project-profile-v4"
    assert profile.identitySummaryZh == profile.officialSummaryZh
    assert profile.coreValueZh is not None
    assert profile.coreValueEvidenceRefs
    assert len(profile.keyDifferentiators) <= 2
    assert {"Agent Skill", "Node.js 渲染/校验工具"}.issubset(profile.productFormsZh)
    assert {"Raven", "Cursor", "Claude Code", "Codex CLI", "OpenCode", "浏览器"}.issubset(
        profile.supportedEnvironmentsZh
    )
    assert {"独立 HTML", "PNG", "SVG", "WebM"}.issubset(profile.deliveryFormsZh)
    assert [capability.title for capability in profile.capabilities[:4]] == [
        "技术图与交互展示",
        "架构变化对比",
        "确定性中间表示",
        "可验证独立交付",
    ]
    assert all(capability.title not in capability.detail for capability in profile.capabilities)
    assert all(capability.evidenceRefs for capability in profile.capabilities)
    assert any(link.path == "archify/SKILL.md" for link in profile.startHere)
    assert any(link.path == "examples" for link in profile.startHere)
    claims = [*profile.productFormsZh, *profile.supportedEnvironmentsZh, *profile.deliveryFormsZh]
    assert all(profile.claimEvidenceRefs[claim] for claim in claims)
    assert all(
        reference in collected.evidence.evidenceIndex
        for claim in claims
        for reference in profile.claimEvidenceRefs[claim]
    )


@pytest.mark.asyncio
async def test_structured_taxonomy_ignores_logos_api_lists_and_translator_guesses(tmp_path: Path) -> None:
    project = _project().model_copy(update={"description": None})
    markdown = """
# Public API Directory
An Awesome List of public APIs maintained by the community.

![Project logo](assets/logo.png)

## Entries
- Weather API: query forecasts from a third-party endpoint.
"""

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/contents"):
            return httpx.Response(200, json=[{"path": "README.md", "type": "file"}])
        return httpx.Response(200, json=_readme_payload(markdown, sha="f" * 40))

    async def translate(_payload):
        return ProfileTranslation(
            summary=EvidenceClaim(text="社区维护的公共 API 资源清单。", evidenceRefs=["readme:section:1"]),
            capabilities=[],
            productForms=[EvidenceClaim(text="完整应用", evidenceRefs=["readme:section:1"])],
            supportedEnvironments=[EvidenceClaim(text="浏览器", evidenceRefs=["readme:section:1"])],
            useCases=[],
            deliveryForms=[
                EvidenceClaim(text="PNG", evidenceRefs=["readme:section:1"]),
                EvidenceClaim(text="API", evidenceRefs=["readme:section:2:item:1"]),
            ],
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com") as client:
        collected = await collect_official_project_profile(
            project,
            "fixture-explosion-a",
            tmp_path,
            client=client,
            translate=True,
            translator=translate,
        )

    assert collected.profile.productFormsZh == ["Awesome List"]
    assert collected.profile.supportedEnvironmentsZh == []
    assert collected.profile.deliveryFormsZh == []


@pytest.mark.parametrize(
    ("raw", "expected_title", "expected_detail"),
    [
        ("架构变化对比 —— 展示新增、删除和重路由。", "架构变化对比", "展示新增、删除和重路由。"),
        ("证据追踪: 保留每个判断对应的官方来源。", "证据追踪", "保留每个判断对应的官方来源。"),
        ("安全边界 - 不执行第三方仓库代码。", "安全边界", "不执行第三方仓库代码。"),
    ],
)
def test_capability_builder_parses_semantic_separators_without_truncation(
    raw: str,
    expected_title: str,
    expected_detail: str,
) -> None:
    capability = _structure_capability(EvidenceClaim(text=raw, evidenceRefs=["readme:section:1"]), 1)

    assert capability.title == expected_title
    assert capability.detail == expected_detail
    assert not (capability.shortDetail or "").endswith("…")


def test_capability_builder_replaces_a_repeated_explicit_title() -> None:
    capability = _structure_capability(
        EvidenceClaim(
            text="架构变化对比：架构变化对比展示新增、删除和重路由。",
            evidenceRefs=["readme:section:1"],
        ),
        1,
    )

    assert capability.title != "架构变化对比"
    assert not capability.detail.startswith(capability.title)


@pytest.mark.parametrize(
    ("title", "detail"),
    [
        ("架构变化对比", "架构变化对比"),
        ("架构变化对比", "架构变化对比：展示新增和删除"),
        ("Architecture Delta", "  architecture-delta  "),
    ],
)
def test_capability_schema_rejects_title_detail_repetition(title: str, detail: str) -> None:
    with pytest.raises(ValueError, match="must not repeat"):
        ServingCapability(title=title, detail=detail, evidenceRefs=["readme:section:1"])


def test_capability_schema_rejects_incomplete_or_unbound_text() -> None:
    with pytest.raises(ValueError):
        ServingCapability(title="架构变化对比", detail="展示新增和删除。", evidenceRefs=[])
    with pytest.raises(ValueError, match="complete"):
        ServingCapability(
            title="架构变化对比",
            detail="展示新增和删除。",
            shortDetail="展示新增…",
            evidenceRefs=["readme:section:1"],
        )
    with pytest.raises(ValueError, match="too long"):
        ServingCapability(
            title="这是一个明显超过十六个中文字符限制的能力标题",
            detail="展示新增和删除。",
            evidenceRefs=["readme:section:1"],
        )


def test_capability_builder_never_slices_a_long_detail_for_short_display() -> None:
    detail = "完整说明" * 30
    capability = _structure_capability(EvidenceClaim(text=detail, evidenceRefs=["readme:section:1"]), 1)

    assert capability.detail == detail
    assert capability.shortDetail is None


@pytest.mark.asyncio
async def test_missing_structured_evidence_is_hidden_instead_of_invented(tmp_path: Path) -> None:
    project = _project().model_copy(update={"description": "A small open source repository."})

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com") as client:
        collected = await collect_official_project_profile(
            project,
            "fixture-explosion-a",
            tmp_path,
            client=client,
            translate=False,
        )

    assert collected.profile.profileState == "partial"
    assert collected.profile.productFormsZh == []
    assert collected.profile.supportedEnvironmentsZh == []
    assert collected.profile.deliveryFormsZh == []
