"""Explicit alternate-edition boundaries survive parsing without hiding this edition."""

import pytest

from app.integrations.rardar import serving_profiles as profiles
from app.integrations.rardar.project_introductions import alternate_edition_section

INTRO = "一个面向本地文件的开源数据处理工具，提供文件索引和转换能力。"
OPEN_FEATURE = "开源版支持读取 CSV 并在本地导出 JSON 文件。"
PAID_FEATURE = "商业版支持托管服务和团队权限控制。"
AFTER_FEATURE = "开源版支持在断网环境中继续处理本地文件。"


@pytest.mark.parametrize(
    "boundary",
    [
        "商业版相较于开源版本的核心优势：",
        "### 商业版独有功能",
        "<summary>开源版不够用？看看商业版</summary>",
    ],
)
def test_short_boundary_does_not_lose_current_edition_or_include_other_edition(boundary):
    markdown = f"# ExampleTool\n\n{INTRO}\n\n## 功能特性\n\n- {OPEN_FEATURE}\n\n{boundary}\n\n- {PAID_FEATURE}\n"
    sections = profiles._parse_readme(markdown, "README.md")
    summary, _, capabilities, *_ = profiles._source_claims(sections, None)
    assert summary == INTRO
    assert OPEN_FEATURE in capabilities
    assert PAID_FEATURE not in capabilities
    alternate = next(section for section in sections if PAID_FEATURE in section.listItems)
    assert alternate_edition_section(alternate)
    assert OPEN_FEATURE not in alternate.listItems
    # A paragraph/HTML summary is not a Markdown heading with a real anchor.
    if not boundary.startswith("###"):
        assert alternate.path == "README.md#功能特性"


def test_closing_alternate_details_returns_to_current_edition_scope():
    markdown = f"""# ExampleTool

{INTRO}

## 功能特性

- {OPEN_FEATURE}

<details>
<summary>开源版不够用？看看商业版</summary>

- {PAID_FEATURE}

</details>

- {AFTER_FEATURE}
"""
    sections = profiles._parse_readme(markdown, "README.md")
    capabilities = profiles._source_claims(sections, None)[2]
    assert OPEN_FEATURE in capabilities
    assert AFTER_FEATURE in capabilities
    assert PAID_FEATURE not in capabilities


def test_next_real_heading_ends_alternate_edition_scope():
    markdown = f"""# ExampleTool

{INTRO}

## 功能特性

- {OPEN_FEATURE}

商业版相较于开源版本的核心优势：

- {PAID_FEATURE}

## 更多功能

- {AFTER_FEATURE}
"""
    sections = profiles._parse_readme(markdown, "README.md")
    capabilities = profiles._source_claims(sections, None)[2]
    assert OPEN_FEATURE in capabilities
    assert AFTER_FEATURE in capabilities
    assert PAID_FEATURE not in capabilities


def test_normal_short_prose_and_code_examples_do_not_create_edition_boundaries():
    markdown = f"""# ExampleTool

{INTRO}

## 功能特性

- {OPEN_FEATURE}

这一段只是普通说明。

```text
商业版相较于开源版本的核心优势：
```

- {AFTER_FEATURE}
"""
    sections = profiles._parse_readme(markdown, "README.md")
    assert not any(alternate_edition_section(section) for section in sections)
    assert {OPEN_FEATURE, AFTER_FEATURE} <= set(profiles._source_claims(sections, None)[2])
