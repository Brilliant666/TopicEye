"""Deterministic, network-free Sub2API stand-in used only by Rardar POC mode."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class MockInvocationTrace:
    request_id: str
    input_hash: str
    reasoning_effort: str
    attempt_count: int
    input_tokens: int
    output_tokens: int


_attempts: dict[str, int] = {}
_latest: dict[str, MockInvocationTrace] = {}


def reset_mock_sub2api() -> None:
    _attempts.clear()
    _latest.clear()


def get_mock_trace(input_hash: str) -> MockInvocationTrace | None:
    return _latest.get(input_hash)


def request_input_hash(*, messages: list, scene: str, reasoning_effort: str) -> str:
    payload = json.dumps(
        {"messages": messages, "scene": scene, "reasoningEffort": reasoning_effort},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _request_payload(messages: list) -> dict[str, Any]:
    if not messages:
        return {}
    content = messages[-1].get("content", "") if isinstance(messages[-1], dict) else ""
    try:
        parsed = json.loads(content)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _project_profile(payload: dict[str, Any], effort: str) -> dict[str, Any]:
    repository = str(payload.get("repository") or "unknown/unknown")
    project_id = str(payload.get("projectId") or "p_000000000000")
    source_revision = str(payload.get("sourceRevision") or "unknown-revision")
    evidence_refs = payload.get("evidenceRefs") or [f"fixture:{repository}"]
    return {
        "repository": repository,
        "projectId": project_id,
        "summaryZh": f"{repository} 提供了可验证、可组合的开发者生产力能力。",
        "coreCapabilities": ["结构化工作流", "可观测运行", "模块化集成"],
        "projectForm": "开发者基础设施与可组合工具链",
        "notablePoint": "用可运行工程边界把复杂任务拆成可验证、可恢复的步骤。",
        "whyTrendingHypothesis": "AI 判断：近期关注可能来自清晰的开发者痛点、可运行示例与持续维护；该判断不改变事实榜名次。",
        "evidenceRefs": evidence_refs,
        "confidence": 0.82,
        "limitations": ["POC 使用确定性 Mock，未调用真实 Sub2API", "爆发原因仍需外部事件证据复核"],
        "sourceRevision": source_revision,
        "model": "gpt-5.6-sol",
        "reasoningEffort": effort,
        "promptVersion": "rardar-project-profile-v1",
        "schemaVersion": 1,
        "generatedAt": "2026-08-24T00:00:00+00:00",
    }


def _requirement_profile(payload: dict[str, Any]) -> dict[str, Any]:
    query = str(payload.get("query") or "寻找可复用的开发者工具")
    repository_url = payload.get("repositoryUrl")
    repository_context = str(repository_url) if repository_url else None
    return {
        "goal": query,
        "mustHave": ["可自托管", "结构化任务编排", "可验证结果"],
        "niceToHave": ["Python API", "PostgreSQL", "异步 Job", "管理后台"],
        "constraints": ["候选必须来自版本化真实索引", "不得由模型编造仓库"],
        "exclude": ["仅有宣传页而无可运行源码的项目"],
        "technologyStack": ["Python", "FastAPI", "PostgreSQL"],
        "deployment": ["本地优先", "未来可部署到 Linux 服务器"],
        "licensePreference": ["优先 OSI 认可的开源许可证"],
        "reuseGranularity": ["whole_product", "module_or_library", "workflow"],
        "acceptanceCriteria": ["可以本地启动", "核心流程有测试", "许可证与集成风险可说明"],
        "repositoryContext": repository_context,
    }


def _comparison(payload: dict[str, Any]) -> dict[str, Any]:
    candidates = payload.get("candidates") if isinstance(payload.get("candidates"), list) else []
    repositories = [
        item.get("repository")
        for item in candidates
        if isinstance(item, dict) and isinstance(item.get("repository"), str)
    ]
    return {
        "selectedRepositories": repositories[:3],
        "comparisonNotes": "同一 RequirementProfile 与标准化候选证据在一次 xhigh 比较任务中处理。",
    }


async def mock_sub2api_completion(
    *,
    messages: list,
    model: str,
    scene: str,
    reasoning_effort: str | None,
) -> Any:
    effort = reasoning_effort or "high"
    input_hash = request_input_hash(messages=messages, scene=scene, reasoning_effort=effort)
    attempt_count = _attempts.get(input_hash, 0) + 1
    _attempts[input_hash] = attempt_count
    input_tokens = max(1, len(json.dumps(messages, ensure_ascii=False)) // 4)
    # Provider request IDs must remain unique across process restarts even though
    # the response body is otherwise deterministic for a given fixture input.
    request_id = f"mock_req_{input_hash[:16]}_{attempt_count}_{uuid4().hex}"
    payload = _request_payload(messages)
    scenario = str(payload.get("mockScenario") or "success")

    trace = MockInvocationTrace(
        request_id=request_id,
        input_hash=input_hash,
        reasoning_effort=effort,
        attempt_count=attempt_count,
        input_tokens=input_tokens,
        output_tokens=0,
    )
    _latest[input_hash] = trace

    if scenario == "timeout":
        raise TimeoutError("mock_sub2api timeout")
    if scenario == "429":
        raise RuntimeError("429 mock_sub2api rate limit")
    if scenario == "5xx":
        raise RuntimeError("503 mock_sub2api upstream unavailable")
    if scenario == "invalid_json":
        content = "not-json"
    elif scenario == "schema_mismatch":
        content = json.dumps({"result": {"unexpected": True}, "providerTrace": {}}, ensure_ascii=False)
    else:
        if scene in {"rardar_project_summary", "rardar_explosion_reason"}:
            result = _project_profile(payload, effort)
        elif scene == "rardar_requirement_profile":
            result = _requirement_profile(payload)
        elif scene == "rardar_candidate_compare":
            result = _comparison(payload)
        else:
            result = {"ok": True, "scene": scene}
        output_tokens = max(1, len(json.dumps(result, ensure_ascii=False)) // 4)
        trace = MockInvocationTrace(
            request_id=request_id,
            input_hash=input_hash,
            reasoning_effort=effort,
            attempt_count=attempt_count,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        _latest[input_hash] = trace
        content = json.dumps(
            {
                "result": result,
                "providerTrace": {
                    "requestId": request_id,
                    "provider": "mock_sub2api",
                    "model": "gpt-5.6-sol",
                    "reasoningEffort": effort,
                    "inputTokens": input_tokens,
                    "cachedTokens": 0,
                    "outputTokens": output_tokens,
                    "attemptCount": attempt_count,
                },
            },
            ensure_ascii=False,
        )

    return SimpleNamespace(
        model=model,
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(
            prompt_tokens=input_tokens,
            completion_tokens=max(1, len(content) // 4),
            prompt_tokens_details=SimpleNamespace(cached_tokens=0),
        ),
    )
