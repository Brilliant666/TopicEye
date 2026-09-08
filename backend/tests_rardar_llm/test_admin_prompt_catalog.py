"""Read-only Rardar catalog references the prompts used by business calls."""

import ast
import inspect

from app.services import prompt_registry_service as registry, rardar_news_quickread as news, rardar_product as product


def test_rardar_catalog_imports_active_prompt_constants():
    expected = {
        "rardar_find_plan": product.FIND_PLAN_SYSTEM_PROMPT,
        "rardar_find_comparison": product.FIND_COMPARISON_SYSTEM_PROMPT,
        "rardar_news_quickread": news.QUICK_READ_SYSTEM_TEMPLATE,
        "rardar_news_title_only": news.QUICK_READ_TITLE_CONTRACT,
        "rardar_news_material": news.QUICK_READ_MATERIAL_CONTRACT,
    }
    entries = [entry for entry in registry._PROMPT_CATALOG if entry["name"] in expected]
    assert len(entries) == len(expected)
    for entry in entries:
        assert registry._import_prompt_content(entry["module"], entry["attr"]) == expected[entry["name"]]
        assert entry["scene"] in {"rardar_find_project_comparison", "rardar_news_quickread"}


def test_find_calls_reference_catalog_constants_not_copied_text():
    for function, name in (
        (product._plan_requirement, "FIND_PLAN_SYSTEM_PROMPT"),
        (product.find_projects, "FIND_COMPARISON_SYSTEM_PROMPT"),
    ):
        tree = ast.parse(inspect.getsource(function))
        assert any(isinstance(node, ast.Name) and node.id == name for node in ast.walk(tree))


def test_news_catalog_keeps_both_material_boundaries():
    title = news.QUICK_READ_SYSTEM_TEMPLATE.format(material_contract=news.QUICK_READ_TITLE_CONTRACT)
    body = news.QUICK_READ_SYSTEM_TEMPLATE.format(material_contract=news.QUICK_READ_MATERIAL_CONTRACT)
    assert "summaryZh MUST be null" in title
    assert "based only on MATERIAL" in body
    assert "discussion are not article evidence" in title
    assert "discussion are not article evidence" in body
