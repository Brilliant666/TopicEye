from __future__ import annotations

import base64
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.integrations.rardar.adapter import RardarIntelligenceAdapter
from app.integrations.rardar.serving_profiles import (
    DerivedPositioning,
    EvidenceClaim,
    ExtractedOfficialHighlight,
    ExtractedOfficialNarrative,
    OfficialNarrativeTranslation,
    OfficialPositioningTranslation,
    ProfileTranslation,
    ProfileTranslationError,
    TranslatedOfficialHighlight,
    _bounded_translation_evidence,
    _dedupe_context_subject,
    _derived_core_value,
    _extract_official_narrative,
    _generation_error_code,
    _github_file_url,
    _load_last_known_good,
    _navigation_noise,
    _official_chinese_positioning,
    _official_english_positioning_is_high_signal,
    _official_positioning_is_high_signal,
    _parse_readme,
    _preferred_chinese_readme,
    _primary_semantic_duplicate,
    _readme_redirect_target,
    _safe_fallback_identity,
    _semantic_structuring_required,
    _source_language,
    _structure_capability,
    _text_issue_codes,
    _translate_official_positioning_with_control,
    _translate_official_with_control,
    _translate_with_control,
    _translation_required,
    _valid_capabilities,
    _validate_official_translation,
    _validate_translation,
    build_official_profiles,
    collect_official_project_profile,
)
from app.integrations.rardar.serving_schemas import PositioningExcludedClause, ServingCapability
from app.services.rardar_llm_control import RardarLLMError

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


def test_single_capability_core_value_is_not_a_copy_of_the_capability_detail() -> None:
    capability = ServingCapability(
        title="公共 API 分类索引",
        detail="维护按主题整理的公共 API 清单，帮助开发者查找可集成的数据与服务接口。",
        evidenceRefs=["readme:section:3"],
        sourceMode="official_translated",
    )

    value, refs = _derived_core_value(
        "一个公共 API 精选列表。",
        [capability],
        [],
        {capability.detail: capability.evidenceRefs},
        {"readme:section:3": "A collective list of free APIs."},
    )

    assert value is not None
    assert capability.detail not in value
    assert refs == ["readme:section:3"]


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


def test_parser_ignores_multiline_html_language_navigation() -> None:
    markdown = """
# Project
<p align="center">
  <a href="README.vi.md">🇻🇳 Tiếng Việt</a> |
  <a href="README.zh.md">🇨🇳 简体中文</a> |
  <a href="README.md">🇺🇸 English</a>
</p>

一个为多种开发环境提供可验证设计智能的开源工具。
"""

    sections = _parse_readme(markdown, "README.zh.md")

    assert sections[0].excerpts == ["一个为多种开发环境提供可验证设计智能的开源工具。"]


def test_textual_language_navigation_cannot_become_rardar_positioning() -> None:
    translation = ProfileTranslation(
        summary=EvidenceClaim(text="这是一个用于生成视频的自动化工具。", evidenceRefs=["description"]),
        positioning=DerivedPositioning(
            positioningZh="简体中文 | English | 日本語 | 版本发布 | 问题反馈",
            includedEvidenceRefs=["readme:section:1"],
            includedRoles=["identity"],
        ),
        capabilities=[],
        productForms=[],
        supportedEnvironments=[],
        useCases=[],
        deliveryForms=[],
    )

    with pytest.raises(ProfileTranslationError, match="rardar_profile_translation_invalid"):
        _validate_translation(translation, {"description", "readme:section:1"})


@pytest.mark.asyncio
async def test_partial_chinese_official_positioning_is_preserved_while_capabilities_are_completed(
    tmp_path: Path,
) -> None:
    project = _project().model_copy(
        update={"repository": "deepseek-ai/deepseek-harness", "description": None, "githubRepositoryId": 1333065091}
    )
    markdown = """
# DeepSeek Harness

DeepSeek Harness（`dsh`）是由 DeepSeek AI 开发的开源 agent harness（智能体框架）。

它构建于**一切皆插件**的架构之上，由 [Cordis](https://example.test/cordis) 驱动，其设计参见论文。

## 运行

默认在 127.0.0.1 启动 Web UI，也可通过 SSH 暴露 URL 或仅启动服务器。
"""

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/contents"):
            return httpx.Response(200, json=[{"path": "README.zh.md", "type": "file"}])
        return httpx.Response(200, json=_readme_payload(markdown, path="README.zh.md", sha="8" * 40))

    async def complete_capability(payload):
        evidence = payload["evidenceIndex"]
        summary_ref = next(reference for reference, text in evidence.items() if "DeepSeek Harness" in text)
        capability_ref = next(reference for reference, text in evidence.items() if "一切皆插件" in text)
        return ProfileTranslation(
            summary=EvidenceClaim(text="一个插件化智能体框架。", evidenceRefs=[summary_ref]),
            positioning=DerivedPositioning(
                positioningZh="一个插件化智能体框架，通过 Cordis 组合扩展能力。",
                includedEvidenceRefs=[capability_ref],
                includedRoles=["identity", "core_mechanism"],
            ),
            capabilities=[
                ServingCapability(
                    title="插件化扩展",
                    detail="通过一切皆插件的架构组合智能体能力，并由 Cordis 驱动扩展。",
                    evidenceRefs=[capability_ref],
                    sourceMode="rardar_derived",
                )
            ],
            productForms=[],
            supportedEnvironments=[],
            useCases=[],
            deliveryForms=[],
        )

    async def unexpected_narrative_model(_payload):
        raise AssertionError("official Chinese positioning must not invoke a narrative model")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com") as client:
        collected = await collect_official_project_profile(
            project,
            "fixture-explosion-a",
            tmp_path,
            client=client,
            translate=True,
            translator=complete_capability,
            narrative_translator=unexpected_narrative_model,
            positioning_translator=unexpected_narrative_model,
        )

    profile = collected.profile
    assert profile.officialNarrativeMode == "rardar_derived"
    assert profile.positioningSourceMode == "official_zh"
    assert profile.positioningZh == "以“一切皆插件”为架构，由 Cordis 驱动。"
    assert profile.positioningEvidenceRefs == ["readme:narrative:positioning"]
    assert profile.officialPositioningZh == profile.positioningZh
    assert profile.officialPositioningEvidenceRefs == profile.positioningEvidenceRefs
    assert collected.translation_calls == 1
    assert [item.sourceMode for item in profile.capabilities] == ["rardar_derived"]
    assert all(marker not in profile.positioningZh for marker in ["Web UI", "SSH", "127.0.0.1", "仅启动服务器"])


@pytest.mark.asyncio
async def test_rardar_positioning_uses_roles_exclusions_and_context_subject_dedupe(tmp_path: Path) -> None:
    project = _project().model_copy(
        update={"repository": "DietrichGebert/ponytail", "description": None, "githubRepositoryId": 1266797999}
    )
    markdown = """
# Ponytail

Ponytail puts a lazy senior developer inside your AI agent.

## How it works

The agent first reads the affected code and traces the real flow, then chooses the first viable rung.

## Validation

Measured in real FastAPI and React repositories using Claude Code sessions and final Git diff output.
"""

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/contents"):
            return httpx.Response(
                200,
                json=[
                    {"path": "README.md", "type": "file"},
                    {"path": "skills", "type": "dir"},
                    {"path": "rules", "type": "dir"},
                    {"path": "plugin.json", "type": "file"},
                ],
            )
        return httpx.Response(200, json=_readme_payload(markdown, sha="9" * 40))

    async def translate(payload):
        refs = set(payload["evidenceIndex"])
        assert {item["text"] for item in payload["structuredPositioningForms"]} == {"技能", "规则集", "插件"}
        how_ref = next(reference for reference in refs if "section:2" in reference)
        validation_ref = next(reference for reference in refs if "section:3" in reference)
        return ProfileTranslation(
            summary=EvidenceClaim(
                text="Ponytail 是让 AI 编程代理优先采用精简实现的技能。",
                evidenceRefs=["readme:section:1"],
            ),
            positioning=DerivedPositioning(
                positioningZh=(
                    "Ponytail 是一套面向 AI 编程代理的技能、规则集与插件，指导代理先理解真实代码流程，"
                    "再选择尽可能精简且保留安全边界的实现。"
                ),
                includedEvidenceRefs=[how_ref],
                includedRoles=["identity", "core_mechanism", "primary_outcome"],
                excludedClauses=[
                    PositioningExcludedClause(
                        role="validation",
                        text="在真实 FastAPI 与 React 仓库的 Claude Code 会话中通过最终 Git diff 测量。",
                        evidenceRefs=[validation_ref],
                    )
                ],
            ),
            capabilities=[],
            productForms=[],
            supportedEnvironments=[],
            useCases=[],
            deliveryForms=[],
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

    profile = collected.profile
    assert profile.positioningSourceMode == "rardar_derived"
    assert profile.positioningZh == (
        "一套面向 AI 编程代理的技能、规则集与插件，指导代理先理解真实代码流程，"
        "再选择尽可能精简且保留安全边界的实现。"
    )
    assert profile.positioningIncludedRoles == ["identity", "core_mechanism", "primary_outcome"]
    assert [item.role for item in profile.positioningExcludedClauses] == ["validation"]
    assert {"技能", "规则集", "插件"}.issubset(profile.productFormsZh)
    assert all(marker not in profile.positioningZh for marker in ["FastAPI", "React", "Claude Code", "Git diff"])


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("Ponytail 是一套面向代理的精简实现规则集。", "一套面向代理的精简实现规则集。"),
        ("Ponytail 通过理解代码流程选择精简实现。", "通过理解代码流程选择精简实现。"),
        ("该项目是一个本地优先工具，用于整理公开仓库。", "一个本地优先工具，用于整理公开仓库。"),
        ("该项目是一款本地优先工具，用于整理公开仓库。", "一款本地优先工具，用于整理公开仓库。"),
        ("这是一个用于管理公开仓库的本地工具。", "用于管理公开仓库的本地工具。"),
        ("Ponytail 是。", "Ponytail 是。"),
    ],
)
def test_context_subject_dedupe_is_grammar_guarded(source: str, expected: str) -> None:
    assert _dedupe_context_subject(source) == expected


def test_positioning_contract_preserves_semantic_clauses_without_string_splitting() -> None:
    value = DerivedPositioning(
        positioningZh="一套可组合的工作流；第二个分句描述由规则引擎驱动的核心机制。",
        includedEvidenceRefs=["readme:section:1"],
        includedRoles=["identity", "core_mechanism"],
        excludedClauses=[
            PositioningExcludedClause(
                role="operation",
                text="运行命令会先启动本地服务。",
                evidenceRefs=["readme:section:2"],
            )
        ],
    )

    assert value.positioningZh.endswith("核心机制。")
    assert "；" in value.positioningZh
    assert value.excludedClauses[0].text.startswith("运行命令")


def test_official_chinese_positioning_never_receives_context_subject_dedupe() -> None:
    source = "Archify 是一套基于 Node.js 的渲染与校验系统。"

    assert _official_chinese_positioning(source) == source


def test_official_english_positioning_rejects_benchmark_and_operation_prose() -> None:
    assert _official_english_positioning_is_high_signal(
        "A rendering engine turns typed input into standalone HTML artifacts."
    )
    assert not _official_english_positioning_is_high_signal(
        "54% less code and 27% faster, measured in real sessions against a baseline; reproduce the benchmark."
    )
    assert not _official_english_positioning_is_high_signal(
        "Run npm install, start the server on localhost, and expose the port through SSH."
    )
    assert not _official_english_positioning_is_high_signal(
        "Building real applications is hard. Other methodologies try to help, but they take away your control."
    )
    assert _official_positioning_is_high_signal("万物皆插件，桌面本身也是插件。", "zh")
    assert _official_positioning_is_high_signal("一款在本地计算机终端中运行的轻量级编程智能体。", "zh")
    assert not _official_positioning_is_high_signal(
        "其他项目 NextLevelBuilder.io | GoClaw.sh | ClaudeKit.cc。",
        "zh",
    )


@pytest.mark.asyncio
async def test_rardar_prompt_requires_complementary_forms_and_preserves_core_safety_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_call(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            value=ProfileTranslation(
                summary=EvidenceClaim(text="面向 AI 编程代理的精简实现规则集。", evidenceRefs=["description"]),
                positioning=DerivedPositioning(
                    positioningZh=(
                        "一套面向 AI 编程代理的技能、规则集与插件，指导代理理解真实代码流程，"
                        "再选择尽可能精简且保留安全边界的实现。"
                    ),
                    includedEvidenceRefs=["description", "readme:section:1"],
                    includedRoles=["identity", "core_mechanism", "primary_outcome"],
                ),
                capabilities=[],
                productForms=[],
                supportedEnvironments=[],
                useCases=[],
                deliveryForms=[],
            )
        )

    monkeypatch.setattr("app.services.rardar_llm_control.call_rardar_structured", fake_call)
    translated = await _translate_with_control(
        {
            "repository": "owner/example",
            "sourceLanguage": "en",
            "evidenceIndex": {
                "description": "A skill, ruleset, and plugin for AI coding agents.",
                "readme:section:1": "Understand the real flow, then keep the smallest safe implementation.",
            },
            "structuredPositioningForms": [
                {"text": "技能", "evidenceRefs": ["description"]},
                {"text": "规则集", "evidenceRefs": ["description"]},
                {"text": "插件", "evidenceRefs": ["description"]},
            ],
        }
    )

    system_prompt = captured["messages"][0]["content"]
    assert "技能、规则集和插件" in system_prompt
    assert "保留安全边界" in system_prompt
    assert "benchmark" in system_prompt
    assert captured["reasoning_effort"] is None
    assert translated.positioning is not None
    assert translated.positioning.includedRoles == ["identity", "core_mechanism", "primary_outcome"]


@pytest.mark.asyncio
async def test_official_translation_calls_preserve_provider_default_effort(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    async def fake_call(**kwargs):
        calls.append(kwargs)
        response_model = kwargs["response_model"]
        if response_model is OfficialNarrativeTranslation:
            value = OfficialNarrativeTranslation(
                translatedTagline="一个项目身份说明。",
                translatedPositioning="一个通过结构化证据说明核心能力的开发工具。",
                translatedHighlights=[
                    TranslatedOfficialHighlight(sourceOrder=1, titleZh="核心能力", detailZh="整理项目证据。")
                ],
            )
        else:
            value = OfficialPositioningTranslation(translatedPositioning="一个通过结构化证据说明核心能力的开发工具。")
        return SimpleNamespace(value=value)

    monkeypatch.setattr("app.services.rardar_llm_control.call_rardar_structured", fake_call)
    await _translate_official_with_control(
        {
            "repository": "owner/example",
            "sourceTagline": "A project identity.",
            "sourcePositioning": "A tool that explains capabilities from structured evidence.",
            "sourceHighlights": [{"sourceOrder": 1, "sourceTitle": "Core", "sourceDetail": "Organize evidence."}],
        }
    )
    await _translate_official_positioning_with_control(
        {
            "repository": "owner/example",
            "sourcePositioning": "A tool that explains capabilities from structured evidence.",
        }
    )

    assert [call["reasoning_effort"] for call in calls] == [None, None]


def test_official_translation_preserves_single_token_technical_titles_but_rejects_untranslated_prose() -> None:
    narrative = ExtractedOfficialNarrative(
        tagline="Turn repositories into maps.",
        tagline_ref="readme:narrative:tagline",
        positioning="A renderer turns typed input into standalone HTML.",
        positioning_ref="readme:narrative:positioning",
        highlights=(
            ExtractedOfficialHighlight(
                source_order=1,
                title="@earendil-works/pi-coding-agent",
                detail="A coding-agent package.",
                evidence_ref="readme:narrative:highlight:1",
            ),
            ExtractedOfficialHighlight(
                source_order=2,
                title="Review changes before merge",
                detail="Compare validated snapshots.",
                evidence_ref="readme:narrative:highlight:2",
            ),
        ),
        issues=(),
    )
    faithful = OfficialNarrativeTranslation(
        translatedTagline="把代码仓库转化为系统地图。",
        translatedPositioning="渲染器把类型化输入转化为独立 HTML。",
        translatedHighlights=[
            TranslatedOfficialHighlight(
                sourceOrder=1,
                titleZh="@earendil-works/pi-coding-agent",
                detailZh="一个编程智能体软件包。",
            ),
            TranslatedOfficialHighlight(
                sourceOrder=2,
                titleZh="合并前审查变化",
                detailZh="比较经过验证的快照。",
            ),
        ],
    )

    _validate_official_translation(faithful, narrative)

    unfaithful = faithful.model_copy(
        update={
            "translatedHighlights": [
                faithful.translatedHighlights[0],
                TranslatedOfficialHighlight(
                    sourceOrder=2,
                    titleZh="Review changes before merge",
                    detailZh="比较经过验证的快照。",
                ),
            ]
        }
    )
    with pytest.raises(ProfileTranslationError, match="rardar_official_translation_content_invalid"):
        _validate_official_translation(unfaithful, narrative)

    navigation_positioning = faithful.model_copy(update={"translatedPositioning": "要进一步了解这个项目："})
    with pytest.raises(ProfileTranslationError, match="rardar_official_positioning_translation_invalid"):
        _validate_official_translation(navigation_positioning, narrative)


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
<p align="center"><strong>Safe Toolkit</strong> 把公开仓库证据整理成可验证的中文项目档案。</p>
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


def test_parser_turns_generic_html_feature_cards_into_evidence_bound_capabilities() -> None:
    markdown = """
<h1 align="center">Desktop Toolkit</h1>

<p align="center"><strong>把本地 Web 服务带到原生桌面并负责本地运行管理。</strong></p>

<p align="center">桌面壳负责窗口、托盘和工作配置，并与上游能力组合。</p>

## 主要功能

<table>
  <tr>
    <td>
      <h3>原生桌面</h3>
      <p>自动启动并管理本地服务，集成系统托盘和桌面窗口。</p>
    </td>
    <td>
      <h3>插件市场</h3>
      <p>提供插件发现、详情、安装与管理，并支持受审数据源。</p>
    </td>
  </tr>
</table>
"""

    sections = _parse_readme(markdown, "README.md")
    overview = next(section for section in sections if section.purpose == "overview")
    capabilities = next(section for section in sections if section.purpose == "capabilities")

    assert overview.excerpts[:2] == [
        "把本地 Web 服务带到原生桌面并负责本地运行管理。",
        "桌面壳负责窗口、托盘和工作配置，并与上游能力组合。",
    ]
    assert capabilities.listItems == [
        "原生桌面 — 自动启动并管理本地服务，集成系统托盘和桌面窗口。",
        "插件市场 — 提供插件发现、详情、安装与管理，并支持受审数据源。",
    ]


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
    assert len(bounded) <= 12
    assert sum(len(key) + len(value) for key, value in bounded.items()) <= 1200
    assert "readme:section:1" in bounded
    assert "readme:section:2" in bounded


def test_translation_evidence_keeps_later_identity_sections_before_early_list_items() -> None:
    evidence = {
        "repository": "官方 GitHub 仓库身份",
        "description": "A collection of public resources",
        "readme:section:1": "Commercial preface " + ("a" * 360),
        **{f"readme:section:1:item:{index}": f"Product {index}" for index in range(1, 9)},
        "readme:section:2": "Learn more",
        "readme:section:3": (
            "The repository is manually curated by community members and organizes resources from many domains."
        ),
    }

    bounded = _bounded_translation_evidence(evidence)

    assert "readme:section:3" in bounded
    assert list(bounded).index("readme:section:3") < list(bounded).index("readme:section:1:item:1")


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
            positioning=DerivedPositioning(
                positioningZh="一个面向开发者的自动化工具包，通过证据绑定生成项目报告并导出独立 HTML 交付物。",
                includedEvidenceRefs=["readme:section:1", "readme:section:2:item:1", "readme:section:2:item:2"],
                includedRoles=["identity", "core_mechanism", "primary_outcome"],
            ),
            capabilities=[
                ServingCapability(
                    title="证据项目报告",
                    detail="生成有证据支撑的项目报告。",
                    shortDetail="生成有证据支撑的项目报告。",
                    evidenceRefs=["readme:section:2:item:1"],
                    sourceMode="official_translated",
                ),
                ServingCapability(
                    title="独立 HTML 交付",
                    detail="导出独立 HTML 交付物。",
                    shortDetail="导出独立 HTML 交付物。",
                    evidenceRefs=["readme:section:2:item:2"],
                    sourceMode="official_translated",
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

    assert first.profile.sourceLabel == "Rardar 整理"
    assert first.profile.officialNarrativeMode == "rardar_derived"
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
    assert collected.profile.sourceLabel == "Rardar 整理"
    assert collected.profile.officialNarrativeMode == "rardar_derived"
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
    assert collected.profile.sourceLabel == "Rardar 整理"
    assert collected.profile.officialNarrativeMode == "rardar_derived"
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
    with pytest.raises(ProfileTranslationError, match="rardar_profile_translation_evidence_mismatch"):
        _validate_translation(
            ProfileTranslation(
                coreValue=EvidenceClaim(text="通过版本化证据降低采用判断的不确定性。", evidenceRefs=["invented"]),
                **common,
            ),
            {"readme:section:1", "readme:section:2"},
        )

    with pytest.raises(ProfileTranslationError, match="rardar_profile_translation_positioning_incomplete"):
        _validate_translation(
            ProfileTranslation(
                positioning=DerivedPositioning(
                    positioningZh=summary.text,
                    includedRoles=["identity", "core_mechanism"],
                    includedEvidenceRefs=["readme:section:1"],
                    excludedClauses=[],
                ),
                coreValue=None,
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
    assert result.profiles[projects[1].githubRepositoryId].profile.sourceLabel == "Rardar 整理"


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
    assert profile.profileSchemaVersion == "rardar-project-profile-v7"
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
    assert {capability.sourceMode for capability in profile.capabilities} == {"deterministic_fallback"}
    assert any(link.path == "archify/SKILL.md" for link in profile.startHere)
    assert any(link.path == "examples" for link in profile.startHere)
    claims = [*profile.productFormsZh, *profile.supportedEnvironmentsZh, *profile.deliveryFormsZh]
    assert all(profile.claimEvidenceRefs[claim] for claim in claims)
    assert all(
        reference in collected.evidence.evidenceIndex
        for claim in claims
        for reference in profile.claimEvidenceRefs[claim]
    )


def test_official_narrative_parser_preserves_archify_titles_and_order() -> None:
    markdown = """
# Archify

**在对话里，把代码仓库或系统描述变成漂亮、可靠、可交互的系统地图。**

Archify 是一套基于 Node.js 的渲染与校验系统，并以 Agent Skill 的形式支持 Raven、Cursor、Claude Code、Codex CLI 和 OpenCode。Agent 负责生成 Typed JSON IR，Archify 再校验并确定性编译为便携、独立的 HTML/SVG 成品。

- **打开就是成品** —— 五种技术图、四套视觉预设、深浅主题、内置品牌徽标，以及显式启用的有限动态
- **合并前先看清架构变化** —— 把两份已校验快照对比为 Before / Delta / After，准确区分新增、删除、语义变化、移动和重路由
- **每次探索都有依据** —— 搜索节点、按需打开版本校验过的源码、追踪作者定义的上下游可达范围与精确路径、对比角色、播放故事，但不编造拓扑
- **一个文件即可放心交付** —— Typed JSON IR 和确定性校验生成独立 HTML，并支持 PNG、SVG、WebM 与 1200×630 分享卡片

## 快速开始
"""

    narrative = _extract_official_narrative(markdown, "README_ZH.md", None)

    assert narrative.mature is True
    assert narrative.tagline == "在对话里，把代码仓库或系统描述变成漂亮、可靠、可交互的系统地图。"
    assert narrative.positioning is not None and "Agent → JSON IR" not in narrative.positioning
    assert [highlight.title for highlight in narrative.highlights] == [
        "打开就是成品",
        "合并前先看清架构变化",
        "每次探索都有依据",
        "一个文件即可放心交付",
    ]
    assert [highlight.source_order for highlight in narrative.highlights] == [1, 2, 3, 4]
    assert narrative.issues == ()


@pytest.mark.asyncio
async def test_structured_chinese_readme_publishes_author_narrative_without_llm(tmp_path: Path) -> None:
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

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/contents"):
            return httpx.Response(200, json=[{"path": "README_ZH.md", "type": "file"}])
        return httpx.Response(200, json=_readme_payload(markdown, path="README_ZH.md", sha="6" * 40))

    async def unexpected_model(_payload):
        raise AssertionError("mature Chinese official narrative must not invoke a model")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com") as client:
        collected = await collect_official_project_profile(
            project,
            "fixture-explosion-a",
            tmp_path,
            client=client,
            translate=True,
            translator=unexpected_model,
            narrative_translator=unexpected_model,
        )

    profile = collected.profile
    assert profile.officialNarrativeMode == "official_zh"
    assert profile.sourceLabel == "官方中文 README"
    assert profile.officialTaglineZh == "把公开仓库证据整理成可验证、可交付的项目地图。"
    assert profile.officialPositioningZh == (
        "这是一套基于 Node.js 的渲染与校验系统，由 Agent 生成 Typed JSON IR，再确定性编译为独立 HTML。"
    )
    assert [item.titleZh for item in profile.officialHighlights] == [
        "打开就是成品",
        "合并前看清变化",
        "每次探索都有依据",
        "一个文件放心交付",
    ]
    assert [item.sourceOrder for item in profile.officialHighlights] == [1, 2, 3, 4]
    assert {item.sourceMode for item in profile.capabilities} == {"official_zh"}
    assert profile.identitySummaryZh == profile.officialTaglineZh
    assert profile.coreValueZh == profile.rardarAssessmentZh
    assert profile.keyDifferentiators == profile.rardarDifferentiators
    assert profile.officialPositioningZh != profile.rardarAssessmentZh
    assert collected.translation_calls == 0


@pytest.mark.asyncio
async def test_structured_english_readme_is_translated_one_to_one(tmp_path: Path) -> None:
    project = _project().model_copy(update={"repository": "fixture-lab/faithful-translation", "description": None})
    markdown = """
# Faithful Map

**Turn source repositories into reliable, interactive system maps.**

Faithful Map is a Node.js renderer and validator that accepts a typed JSON IR and compiles standalone HTML.

- **Open a finished artifact** — Produce an interactive standalone HTML file.
- **Review changes before merge** — Compare validated Before, Delta, and After snapshots.
- **Keep exploration grounded** — Bind each conclusion to versioned source evidence.

## Installation
"""
    observed_payload: dict | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/contents"):
            return httpx.Response(200, json=[{"path": "README.md", "type": "file"}])
        return httpx.Response(200, json=_readme_payload(markdown, sha="7" * 40))

    async def translate_official(payload):
        nonlocal observed_payload
        observed_payload = payload
        return OfficialNarrativeTranslation(
            translatedTagline="把源码仓库转化为可靠、可交互的系统地图。",
            translatedPositioning="Faithful Map 是一套 Node.js 渲染与校验系统，接收 Typed JSON IR 并编译为独立 HTML。",
            translatedHighlights=[
                TranslatedOfficialHighlight(
                    sourceOrder=1, titleZh="打开即是成品", detailZh="生成可交互的独立 HTML 文件。"
                ),
                TranslatedOfficialHighlight(
                    sourceOrder=2, titleZh="合并前审查变化", detailZh="对比已校验的 Before、Delta 与 After 快照。"
                ),
                TranslatedOfficialHighlight(
                    sourceOrder=3, titleZh="让探索有据可查", detailZh="把每项结论绑定到版本化源码证据。"
                ),
            ],
        )

    async def unexpected_assessment(_payload):
        raise AssertionError("mature official narrative must not use the weak-source rewrite path")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com") as client:
        collected = await collect_official_project_profile(
            project,
            "fixture-explosion-a",
            tmp_path,
            client=client,
            translate=True,
            translator=unexpected_assessment,
            narrative_translator=translate_official,
        )

    profile = collected.profile
    assert observed_payload is not None
    assert [item["sourceOrder"] for item in observed_payload["sourceHighlights"]] == [1, 2, 3]
    assert profile.officialNarrativeMode == "official_translated"
    assert profile.sourceLabel == "官方 README（译）"
    assert [item.sourceTitle for item in profile.officialHighlights] == [
        "Open a finished artifact",
        "Review changes before merge",
        "Keep exploration grounded",
    ]
    assert [item.titleZh for item in profile.officialHighlights] == [
        "打开即是成品",
        "合并前审查变化",
        "让探索有据可查",
    ]
    assert [item.sourceOrder for item in profile.officialHighlights] == [1, 2, 3]
    official_claims = {(item.titleZh, item.detailZh) for item in profile.officialHighlights}
    assert all((item.title, item.detail) not in official_claims for item in profile.rardarDifferentiators)
    assert [item.evidenceRefs for item in profile.officialHighlights] == [
        ["readme:narrative:highlight:1"],
        ["readme:narrative:highlight:2"],
        ["readme:narrative:highlight:3"],
    ]
    assert {item.sourceMode for item in profile.capabilities} == {"official_translated"}
    assert collected.translation_calls == 1


def test_serving_profile_builder_contains_no_repository_specific_copy() -> None:
    source = Path(collect_official_project_profile.__code__.co_filename).read_text(encoding="utf-8").casefold()

    for forbidden in {
        "tt-a1i",
        "archify",
        "deepseek-harness",
        "ponytail",
        "1211139949",
        "1333065091",
        "1266797999",
    }:
        assert forbidden not in source
    assert 'if "archify" in repository' not in source


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
        (
            "有 AI 项目记录、需要梳理事实：先用 /asu-recap 区分个人动作、交付阶段与效果证据。",
            "项目事实复盘",
            "先用 /asu-recap 区分个人动作、交付阶段与效果证据。",
        ),
        ("支持多种 高清视频 尺寸", "多规格高清视频输出", "支持多种高清视频尺寸"),
        ("支持 批量视频生成，可以一次生成多个视频", "批量视频生成", "支持批量视频生成，可以一次生成多个视频"),
        ("插件：扩展窗格和工作流。浏览插件市场 →", "插件化工作流扩展", "扩展窗格和工作流"),
        (
            "智能体也能使用 herdr：纯 socket api：智能体可以创建窗格、读取输出、互相等待。智能体技能 →",
            "智能体也能使用 herdr",
            "纯 socket api：智能体可以创建窗格、读取输出、互相等待",
        ),
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


def test_capability_validation_rejects_foreign_evidence_and_non_capability_noise() -> None:
    allowed = {"readme:section:1"}
    capabilities = [
        ServingCapability(
            title="证据绑定",
            detail="把项目结论绑定到当前仓库中可核验的官方资料。",
            evidenceRefs=["readme:section:1"],
            sourceMode="rardar_derived",
        ),
        ServingCapability(
            title="跨仓库串线",
            detail="这条能力错误引用了另一个项目的证据。",
            evidenceRefs=["readme:foreign:section:1"],
            sourceMode="rardar_derived",
        ),
        ServingCapability(
            title="快速开始",
            detail="运行 npm install 后启动本地服务。",
            evidenceRefs=["readme:section:1"],
            sourceMode="deterministic_fallback",
        ),
        ServingCapability(
            title="单个 Rust 二进制",
            detail="运行在你已经在用的任何终端里。",
            evidenceRefs=["readme:section:1"],
            sourceMode="official_zh",
        ),
    ]

    valid, issues = _valid_capabilities(capabilities, allowed)

    assert [item.title for item in valid] == ["证据绑定"]
    assert "capability_evidence_invalid" in issues
    assert "capability_invalid_content" in issues


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


def test_translation_and_semantic_structuring_are_independent_decisions() -> None:
    assert _translation_required("zh", True) is False
    assert (
        _semantic_structuring_required(
            requested=True,
            source_language="zh",
            source_summary="一个面向中文求职流程的技能集合。",
            description=None,
            official_positioning=None,
        )
        is True
    )


def test_primary_positioning_rejects_restatements_but_allows_added_mechanism() -> None:
    assert _primary_semantic_duplicate(
        "这是一个轻量级编码代理。",
        "它是一个轻量级编码代理。",
    )
    assert _primary_semantic_duplicate(
        "一个对 Grok Bot 0.18.0 macOS 应用进行非官方、面向源码重构与扩展的项目。",
        "这是对公开发布的 Grok Bot 0.18.0 macOS 应用进行的非官方、面向源码的重构与扩展。",
    )
    assert not _primary_semantic_duplicate(
        "一个用于整理项目证据的工作台。",
        "一个用于整理项目证据的工作台，通过规则引擎连接原文与交付结果。",
    )


@pytest.mark.asyncio
async def test_weak_chinese_readme_still_runs_semantic_structuring(tmp_path: Path) -> None:
    project = _project().model_copy(update={"description": None})
    markdown = """
# 求职工作流

这是一个面向中文求职流程的技能集合。

- 组织简历分析、岗位搜索和面试准备。
"""
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/contents"):
            return httpx.Response(200, json=[{"path": "README.md", "type": "file"}])
        return httpx.Response(200, json=_readme_payload(markdown, sha="c" * 40))

    async def structure(_payload):
        nonlocal calls
        calls += 1
        return ProfileTranslation(
            summary=EvidenceClaim(text="一个面向中文求职流程的技能集合。", evidenceRefs=["readme:section:1"]),
            positioning=DerivedPositioning(
                positioningZh="一套面向中文求职流程的技能工作流，通过组织简历分析、岗位搜索和面试准备覆盖主要环节。",
                includedEvidenceRefs=["readme:section:1", "readme:section:1:item:1"],
                includedRoles=["identity", "core_mechanism", "primary_outcome"],
            ),
            capabilities=[
                ServingCapability(
                    title="求职流程组织",
                    detail="组织简历分析、岗位搜索和面试准备，覆盖中文求职的主要阶段。",
                    evidenceRefs=["readme:section:1:item:1"],
                    sourceMode="rardar_derived",
                )
            ],
            productForms=[],
            supportedEnvironments=[],
            useCases=[],
            deliveryForms=[],
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com") as client:
        collected = await collect_official_project_profile(
            project,
            "fixture-explosion-a",
            tmp_path,
            client=client,
            translate=True,
            translator=structure,
        )

    assert calls == 1
    assert collected.profile.translationState == "not_needed"
    assert collected.profile.positioningSourceMode == "rardar_derived"
    assert collected.profile.positioningZh is not None


@pytest.mark.asyncio
async def test_schema_invalid_structuring_gets_one_bounded_repair_attempt(tmp_path: Path) -> None:
    project = _project().model_copy(update={"description": None})
    markdown = """
# 证据工作台

这是一个用于整理项目证据的工作台。

- 通过规则引擎连接原文与交付结果。
"""
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/contents"):
            return httpx.Response(200, json=[{"path": "README.md", "type": "file"}])
        return httpx.Response(200, json=_readme_payload(markdown, sha="7" * 40))

    async def structure(payload):
        nonlocal calls
        calls += 1
        assert payload["validationAttempt"] == calls
        positioning_refs = ["missing:evidence"] if calls == 1 else ["readme:section:1", "readme:section:1:item:1"]
        return ProfileTranslation(
            summary=EvidenceClaim(text="一个用于整理项目证据的工作台。", evidenceRefs=["readme:section:1"]),
            positioning=DerivedPositioning(
                positioningZh="一个整理项目证据的工作台，通过规则引擎连接原文与交付结果。",
                includedEvidenceRefs=positioning_refs,
                includedRoles=["identity", "core_mechanism", "primary_outcome"],
            ),
            capabilities=[
                ServingCapability(
                    title="证据关联",
                    detail="通过规则引擎把项目原文连接到可核验的交付结果。",
                    evidenceRefs=["readme:section:1:item:1"],
                    sourceMode="rardar_derived",
                )
            ],
            productForms=[],
            supportedEnvironments=[],
            useCases=[],
            deliveryForms=[],
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com") as client:
        collected = await collect_official_project_profile(
            project,
            "fixture-explosion-a",
            tmp_path,
            client=client,
            translate=True,
            translator=structure,
        )

    assert calls == 2
    assert collected.translation_calls == 2
    assert collected.profile.positioningSourceMode == "rardar_derived"
    assert collected.generation_failures == ()


@pytest.mark.parametrize(
    ("stage", "error", "expected"),
    [
        ("translation", RardarLLMError("rardar_llm_unavailable", classification="timeout"), "translation_timeout"),
        (
            "translation",
            RardarLLMError("rardar_llm_unavailable", classification="rate_limited"),
            "translation_rate_limited",
        ),
        (
            "translation",
            RardarLLMError("rardar_llm_unavailable", classification="provider_error"),
            "translation_provider_error",
        ),
        (
            "positioning",
            RardarLLMError("rardar_llm_invalid_output", classification="invalid_json"),
            "positioning_invalid_json",
        ),
        (
            "positioning",
            RardarLLMError("rardar_llm_invalid_output", classification="schema_invalid"),
            "positioning_schema_invalid",
        ),
        (
            "positioning",
            RardarLLMError("rardar_llm_invalid_output", classification="empty"),
            "positioning_empty",
        ),
        (
            "positioning",
            ProfileTranslationError("rardar_profile_translation_evidence_mismatch"),
            "positioning_evidence_mismatch",
        ),
    ],
)
def test_generation_failures_keep_stable_error_categories(stage: str, error: Exception, expected: str) -> None:
    assert _generation_error_code(stage, error) == expected


@pytest.mark.asyncio
async def test_model_failure_uses_evidence_bound_deterministic_chinese_fallback(tmp_path: Path) -> None:
    project = _project().model_copy(update={"description": None})
    markdown = """
# 任务工作台

这是一个用于自动整理开发任务并持续保存处理结果的工作台。

流程编排：通过规则引擎组织输入、检查和交付结果，并把每一步结果交给后续流程继续处理。
"""

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/contents"):
            return httpx.Response(200, json=[{"path": "README.md", "type": "file"}])
        return httpx.Response(200, json=_readme_payload(markdown, sha="d" * 40))

    async def timeout(_payload):
        raise TimeoutError("provider timeout")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com") as client:
        collected = await collect_official_project_profile(
            project,
            "fixture-explosion-a",
            tmp_path,
            client=client,
            translate=True,
            translator=timeout,
        )

    assert collected.deterministic_fallback_used is True
    assert collected.profile.positioningSourceMode == "official_zh"
    assert collected.profile.positioningZh is not None
    assert collected.profile.positioningEvidenceRefs
    assert {item.sourceMode for item in collected.profile.capabilities} == {"deterministic_fallback"}
    assert not _text_issue_codes(collected.profile.positioningZh)
    assert any(failure.code == "positioning_timeout" and failure.resolved for failure in collected.generation_failures)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com") as client:
        cached = await collect_official_project_profile(
            project,
            "fixture-explosion-a",
            tmp_path,
            client=client,
            translate=True,
            translator=timeout,
        )

    assert cached.translation_calls == 0
    assert cached.deterministic_fallback_used is True


@pytest.mark.asyncio
async def test_last_known_good_reuse_requires_the_exact_evidence_fingerprint(tmp_path: Path) -> None:
    project = _project().model_copy(update={"description": None})
    markdown = """
# Evidence Toolkit

An evidence-backed toolkit for organizing project research.

## Features

- Connect every summary to a saved repository excerpt.
"""

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/contents"):
            return httpx.Response(200, json=[{"path": "README.md", "type": "file"}])
        return httpx.Response(200, json=_readme_payload(markdown, sha="e" * 40))

    async def healthy(_payload):
        return ProfileTranslation(
            summary=EvidenceClaim(text="一个用仓库证据组织项目研究的工具包。", evidenceRefs=["readme:section:1"]),
            positioning=DerivedPositioning(
                positioningZh="一个以仓库证据组织项目研究的工具包，通过把摘要连接到已保存的原文来保留可追溯性。",
                includedEvidenceRefs=["readme:section:1", "readme:section:2:item:1"],
                includedRoles=["identity", "core_mechanism", "primary_outcome"],
            ),
            capabilities=[
                ServingCapability(
                    title="证据追踪",
                    detail="把每份项目摘要连接到已保存的仓库原文，以保留可追溯性。",
                    evidenceRefs=["readme:section:2:item:1"],
                    sourceMode="official_translated",
                )
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
            translator=healthy,
        )

    shutil.rmtree(tmp_path / "profiles", ignore_errors=True)
    shutil.rmtree(tmp_path / "rardar-assessments", ignore_errors=True)

    async def unavailable(_payload):
        raise RuntimeError("provider unavailable")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com") as client:
        second = await collect_official_project_profile(
            project,
            "fixture-explosion-a",
            tmp_path,
            client=client,
            translate=True,
            translator=unavailable,
        )

    assert second.last_known_good_available is True
    assert second.last_known_good_reused is True
    assert second.profile == first.profile
    changed_evidence = first.evidence.model_copy(update={"digest": "f" * 64})
    value, available, fingerprint = _load_last_known_good(
        tmp_path,
        project,
        "fixture-explosion-a",
        changed_evidence,
    )
    assert value is None
    assert available is False
    assert fingerprint != second.last_known_good_fingerprint


@pytest.mark.asyncio
async def test_v7_capability_upgrade_preserves_v6_identity_and_positioning_for_exact_evidence(
    tmp_path: Path,
) -> None:
    project = _project().model_copy(update={"description": None})
    markdown = """
# Evidence Workbench

An evidence workbench for reviewing open-source projects.

## Features

- Bind every project decision to a saved repository excerpt.
"""

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/contents"):
            return httpx.Response(200, json=[{"path": "README.md", "type": "file"}])
        return httpx.Response(200, json=_readme_payload(markdown, sha="6" * 40))

    async def original(_payload):
        return ProfileTranslation(
            summary=EvidenceClaim(text="一个审阅开源项目证据的工作台。", evidenceRefs=["readme:section:1"]),
            positioning=DerivedPositioning(
                positioningZh="一个开源项目审阅工作台，通过保存仓库原文来约束后续采用决策。",
                includedEvidenceRefs=["readme:section:1", "readme:section:2:item:1"],
                includedRoles=["identity", "core_mechanism", "primary_outcome"],
            ),
            capabilities=[
                ServingCapability(
                    title="证据绑定",
                    detail="把项目采用决策连接到已保存的仓库原文。",
                    evidenceRefs=["readme:section:2:item:1"],
                    sourceMode="official_translated",
                )
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
            translator=original,
        )

    lkg_path = next((tmp_path / "last-known-good" / str(project.githubRepositoryId)).glob("*.json"))
    wrapper = json.loads(lkg_path.read_text(encoding="utf-8"))
    legacy = first.profile.model_copy(
        update={
            "profileSchemaVersion": "rardar-project-profile-v6",
            "promptVersion": "rardar-project-profile-zh-v13",
            "rardarAssessmentPromptVersion": "rardar-assessment-zh-v10",
        }
    )
    wrapper.update(
        {
            "profile": legacy.model_dump(mode="json"),
            "profileSchemaVersion": "rardar-project-profile-v6",
            "promptVersion": "rardar-project-profile-zh-v13",
        }
    )
    lkg_path.write_text(json.dumps(wrapper, ensure_ascii=False), encoding="utf-8")
    shutil.rmtree(tmp_path / "profiles", ignore_errors=True)
    shutil.rmtree(tmp_path / "rardar-assessments", ignore_errors=True)

    async def revised(_payload):
        return ProfileTranslation(
            summary=EvidenceClaim(text="这句新身份不得覆盖已验证文案。", evidenceRefs=["readme:section:1"]),
            positioning=DerivedPositioning(
                positioningZh="这句新定位也不得覆盖已验证文案，但仍有完整机制与结果。",
                includedEvidenceRefs=["readme:section:1", "readme:section:2:item:1"],
                includedRoles=["identity", "core_mechanism", "primary_outcome"],
            ),
            capabilities=[
                ServingCapability(
                    title="原文追踪",
                    detail="保存项目采用判断对应的仓库摘录，以便后续复核。",
                    evidenceRefs=["readme:section:2:item:1"],
                    sourceMode="official_translated",
                )
            ],
            productForms=[],
            supportedEnvironments=[],
            useCases=[],
            deliveryForms=[],
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com") as client:
        upgraded = await collect_official_project_profile(
            project,
            "fixture-explosion-a",
            tmp_path,
            client=client,
            translate=True,
            translator=revised,
        )

    assert upgraded.profile.identitySummaryZh == first.profile.identitySummaryZh
    assert upgraded.profile.positioningZh == first.profile.positioningZh
    assert upgraded.profile.positioningEvidenceRefs == first.profile.positioningEvidenceRefs
    assert [item.title for item in upgraded.profile.capabilities] == ["原文追踪"]
    assert upgraded.profile.profileSchemaVersion == "rardar-project-profile-v7"


def test_navigation_and_placeholder_primary_copy_is_never_publishable() -> None:
    assert _navigation_noise("herdr.dev · 安装 · 快速开始 · 文档") is True
    assert "navigation_noise" in _text_issue_codes("Home · Docs · Install · Quick Start")
    assert "placeholder_text" in _text_issue_codes("翻译待补全：A collective list of free APIs")
    assert "placeholder_text" in _text_issue_codes("官方资料不足，当前仅展示仓库身份。")


@pytest.mark.parametrize(
    "positioning",
    [
        "翻译待补全：This is a project positioning placeholder.",
        "<div>这是一个通过证据连接原文与交付结果的工具。</div>",
        "herdr.dev · 安装 · 快速开始 · 文档",
        "这是一个工具。 " + "This untranslated positioning remains long English product prose. " * 5,
    ],
)
def test_generated_positioning_rejects_every_publication_noise_class(positioning: str) -> None:
    value = ProfileTranslation(
        summary=EvidenceClaim(text="这是一个用于整理项目证据的工具。", evidenceRefs=["description"]),
        positioning=DerivedPositioning(
            positioningZh=positioning,
            includedEvidenceRefs=["description"],
            includedRoles=["core_mechanism"],
        ),
        capabilities=[],
        productForms=[],
        supportedEnvironments=[],
        useCases=[],
        deliveryForms=[],
    )

    with pytest.raises(ProfileTranslationError, match="rardar_profile_translation_invalid"):
        _validate_translation(value, {"description"})
