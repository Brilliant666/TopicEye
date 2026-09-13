"""Introduction selection must not mistake translation credits for purpose."""

from types import SimpleNamespace

import pytest

from app.integrations.rardar.project_introductions import (
    official_summary_replacement,
    readable_chinese_introduction,
)
from app.integrations.rardar.serving_profiles import _extract_official_narrative, _parse_readme, _source_claims

CREDIT = "简体中文版由维护者创建，文字由贡献者润色。感谢。"
PURPOSE = "下载课程、视频和书籍，然后对保存的内容进行转写、转换、阅读和学习。一个免费的桌面应用，不用命令行。"


@pytest.mark.parametrize("text", [
    None, "", CREDIT, "感谢所有参与翻译和校对的贡献者。", "为开发者而生！",
    "让开发更美好。", "翻译待补全", "English | 中文 | 日本語", "![状态](https://example.com/badge.svg)",
])
def test_non_introductions_do_not_qualify(text):
    assert not readable_chinese_introduction(text)


@pytest.mark.parametrize("text", [
    PURPOSE, "一个支持离线全文搜索的中文文档工具。", "提供感谢信生成和模板管理的桌面应用。",
])
def test_readable_partial_introduction_does_not_require_full_profile(text):
    assert readable_chinese_introduction(text)


def test_actual_readme_selection_skips_translation_credit():
    # Minimal public-source reproduction; no repository-name special case.
    markdown = f'<h1>Example</h1>\n\n<p><sub>{CREDIT}</sub></p>\n\n<p><b>{PURPOSE}</b></p>\n\n## 安装\n'
    narrative = _extract_official_narrative(markdown, "README_zh_CN.md", None)
    summary, ref, *_ = _source_claims(_parse_readme(markdown, "README_zh_CN.md"), None)
    assert narrative.tagline == PURPOSE
    assert summary == PURPOSE
    assert ref == "readme:section:1"


def test_replacement_is_exact_existing_chinese_evidence_without_timestamp_changes():
    evidence = SimpleNamespace(
        readmePath="README_zh_CN.md",
        evidenceIndex={"readme:narrative:positioning": "README_zh_CN.md: " + PURPOSE},
    )
    assert official_summary_replacement(CREDIT, evidence) == (PURPOSE, ["readme:narrative:positioning"])
    assert official_summary_replacement(PURPOSE, evidence) is None
    evidence.evidenceIndex = {"readme:narrative:positioning": "README.md: Download videos and courses."}
    assert official_summary_replacement(CREDIT, evidence) is None
