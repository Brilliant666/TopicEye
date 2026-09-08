"""Exercise the real JSON decode and strict Python validation boundary."""

import json

import pytest

from app.schemas.rardar_product import FindWireComparison
from app.services import rardar_llm_control as control


@pytest.mark.asyncio
async def test_planner_failure_preserves_maximum_length_requirement(monkeypatch):
    from app.schemas.rardar_product import FindProjectRequest, RequirementCheck
    from app.services import rardar_product

    async def unavailable(**_kwargs):
        raise control.RardarLLMError("rardar_llm_unavailable")

    monkeypatch.setattr(rardar_product, "call_rardar_structured", unavailable)
    requirement = "文档需求" * 300
    profile = await rardar_product._plan_requirement(FindProjectRequest(requirement=requirement))
    assert profile.purpose == requirement
    assert profile.mustHave == [requirement]
    check = RequirementCheck(requirement=requirement, status="unknown", reason="资料尚未核实")
    assert check.requirement == requirement


@pytest.mark.asyncio
async def test_find_json_reuse_type_survives_real_structured_boundary(monkeypatch):
    payload = {
        "candidates": [
            {
                "repository": "example/tool",
                "whatItDoes": "公开资料有限",
                "whyMatched": "检索召回待核对",
                "reusableParts": [],
                "integrationCost": "unknown",
                "risks": [],
                "recommendation": "阅读官方文档",
                "reuseType": "reference_only",
                "requirementChecks": [
                    {"conditionId": "c1", "status": "unknown", "reason": "没有足够资料", "evidenceRefs": []}
                ],
                "evidenceRefs": ["repository"],
            }
        ],
        "overallConclusion": "资料不足，不能确认匹配",
    }

    async def provider(*_args, **_kwargs):
        return json.dumps(payload), {"provider": "mock", "model_name": "mock"}

    monkeypatch.setattr(control, "call_llm_with_metadata", provider)
    result = await control.call_rardar_structured(
        scene=control.RardarLLMScene.FIND_PROJECT_COMPARISON,
        messages=[{"role": "user", "content": "test"}],
        response_model=FindWireComparison,
        prompt_version="rardar-find-project-v4",
        schema_version="rardar-find-project-schema-v3",
    )
    assert result.value.candidates[0].reuseType == "reference_only"
