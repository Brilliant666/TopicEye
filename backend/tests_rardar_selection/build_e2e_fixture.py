"""Build a deterministic Selection projection for isolated browser tests."""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
from pathlib import Path

import httpx

from app.integrations.rardar.selection import build_selection
from app.integrations.rardar.selection_serving import build_selection_serving, install_selection_serving
from app.services.rardar_llm_control import (
    RardarLLMMetadata,
    RardarLLMResult,
    RardarLLMScene,
)
from tests_rardar_selection.source_fixture import loaded_source


def _metadata(scene: RardarLLMScene) -> RardarLLMMetadata:
    return RardarLLMMetadata(
        scene=scene.value,
        routing_group="rardar",
        model_display_name="e2e-selection-model",
        model_id=1,
        provider="mock",
        reasoning_effort="high",
        prompt_version=None,
        schema_version=None,
        latency_ms=1,
        usage={"input_tokens": 5, "cached_tokens": 0, "output_tokens": 5},
        cache_hit=False,
        result_state="completed",
    )


async def _caller(*, scene, messages, reasoning_effort, cache_identity):
    del reasoning_effort
    assert len(cache_identity) == 64
    payload = json.loads(messages[1]["content"])
    repository = str(payload.get("repository", ""))
    if scene == RardarLLMScene.WORTH_SEEING_GATE:
        if repository == "negative-control/case-1":
            result = {
                "scopeStatus": "out_of_scope",
                "valueVerdict": "weak",
                "reasonCandidates": [],
                "counterEvidenceIds": ["E01"],
                "confidence": "high",
            }
        elif repository.startswith("negative-control/"):
            result = {
                "scopeStatus": "in_scope",
                "valueVerdict": "weak",
                "reasonCandidates": [],
                "counterEvidenceIds": ["E01"],
                "confidence": "high",
            }
        else:
            result = {
                "scopeStatus": "in_scope",
                "valueVerdict": "strong",
                "reasonCandidates": [
                    {
                        "reason": "directly_reusable",
                        "supported": True,
                        "evidenceIds": ["E01"],
                    }
                ],
                "counterEvidenceIds": [],
                "confidence": "high",
            }
    elif scene == RardarLLMScene.WORTH_SEEING_MEANINGFUL_CHANGE:
        result = {
            "meaningfulRelease": "yes",
            "meaningfulUpdate": "no",
            "evidenceIds": ["T01"],
            "confidence": "high",
        }
    else:
        result = {
            "identitySummaryZh": f"{repository} 是一个提供可组合模块与清晰工程入口的开源开发工具。",
            "whyWorthSeeingZh": "它提供可以直接检查和接入的 SDK、示例与模块边界，适合验证复用价值。",
            "whyNowZh": "近期发布包含有证据支持的实质能力变化，值得现在重新评估。",
            "reusableAssets": ["SDK", "适配器"],
            "bestFit": ["需要组合自动化工作流的开发者"],
            "evidenceIds": ["E01", "T01"],
        }
    return RardarLLMResult(json.dumps(result, ensure_ascii=False), _metadata(scene))


def _github(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/contents"):
        return httpx.Response(
            200,
            json=[
                {"path": "README.md", "type": "file"},
                {"path": "src", "type": "dir"},
                {"path": "examples", "type": "dir"},
                {"path": "pyproject.toml", "type": "file"},
            ],
        )
    if request.url.path.endswith("/readme"):
        markdown = """# 可复用自动化工具

一个为开发者提供可组合 SDK、连接器和命令行入口的自动化工具。

它通过结构化适配器组合重复工作流，帮助应用在发布前验证输入和输出。

## 核心能力
- **可组合 SDK** —— 提供连接器与命令行工作流，支持按任务组合公开接口。
- **结构化验证** —— 对输入和输出执行校验，并生成可复核的结果。

## 快速开始
在应用中调用公开 SDK 接口并组合所需适配器。
"""
        return httpx.Response(
            200,
            json={
                "sha": "a" * 40,
                "path": "README.md",
                "encoding": "base64",
                "content": base64.b64encode(markdown.encode()).decode(),
            },
            headers={"etag": '"selection-e2e"'},
        )
    if request.url.path.endswith("/releases/latest"):
        return httpx.Response(
            200,
            json={
                "id": 20260903,
                "tag_name": "v2.0.0",
                "name": "Reusable SDK release",
                "body": "Adds a documented adapter API and complete examples.",
            },
            headers={"content-type": "application/json"},
        )
    return httpx.Response(404, json={})


async def _build(target: Path) -> dict[str, object]:
    source = loaded_source(target)
    async with httpx.AsyncClient(
        base_url="https://api.github.com",
        transport=httpx.MockTransport(_github),
    ) as client:
        built = await build_selection(
            source=source,
            cache_root=target / "selection-e2e-cache",
            caller=_caller,
            github_client=client,
        )
    assert built.profiles.translation_calls == 0
    installed = install_selection_serving(target.resolve(), build_selection_serving(built))
    return {
        "status": "healthy",
        "selectionGenerationId": installed.selection_generation_id,
        "sourceObservationSetId": installed.source_observation_set_id,
        "publishedCount": built.artifact.publishedCount,
        "modelCalls": built.artifact.usage.modelCalls,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the isolated Selection E2E fixture")
    parser.add_argument("--target", type=Path, required=True)
    arguments = parser.parse_args()
    print(json.dumps(asyncio.run(_build(arguments.target)), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
