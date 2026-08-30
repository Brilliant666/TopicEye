"""Minimal process-level host for Adapter HTTP/UI tests; no database lifespan."""

import asyncio
import copy
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.api.v1.rardar import router
from app.integrations.rardar import RardarArtifactError
from app.integrations.rardar.serving import ServingProjectionError
from app.services.rardar_intelligence import load_explosion_board, load_project_detail, load_today_snapshot

app = FastAPI()
app.include_router(router, prefix="/api/v1")

_FIXTURE_CAPABILITIES = [
    {
        "title": "完整事实说明",
        "detail": "保留经过验证的完整能力事实，不使用省略号截断成半句话。",
        "shortDetail": "保留完整能力事实，避免截断。",
        "evidenceRefs": ["description"],
    },
    {
        "title": "可验证工程交付",
        "detail": "把工程输出绑定到可以复核的官方仓库证据。",
        "shortDetail": None,
        "evidenceRefs": ["description"],
    },
    {
        "title": "清晰使用边界",
        "detail": "说明适用范围和限制，避免把推断包装成项目事实。",
        "shortDetail": None,
        "evidenceRefs": ["description"],
    },
    {
        "title": "第四项完整能力",
        "detail": "只在项目详情中保留，不挤占今日榜卡片的信息密度。",
        "shortDetail": None,
        "evidenceRefs": ["description"],
    },
]

_FIXTURE_DIFFERENTIATORS = [
    {
        "title": "证据驱动",
        "detail": "关键结论都绑定到可复核的官方仓库证据，而不是依赖宣传性描述。",
        "shortDetail": "结论可以回到官方仓库逐项复核。",
        "evidenceRefs": ["description"],
    },
    {
        "title": "采用边界清晰",
        "detail": "在展示能力的同时说明适用范围，帮助开发者更快判断是否值得复用。",
        "shortDetail": "能力与采用边界放在同一条阅读路径。",
        "evidenceRefs": ["description"],
    },
]

_KNOWN_TOP20_REPOSITORIES = {
    11: "browser-use/browser-use",
    12: "anywhere-labs/dsh-desktop",
    14: "firecrawl/firecrawl",
    15: "openai/codex",
    17: "b-nnett/grok-bot-0.18-reconstructed",
    18: "ayghri/i-have-adhd",
    19: "thedotmack/claude-mem",
    20: "herdrdev/herdr",
}


def _fixture_identity(repository: str) -> str:
    return f"{repository} 是一个把公开仓库能力整理成清晰中文项目认知的开发工具。"


def _apply_v4_profile(payload: dict, repository: str) -> None:
    identity = _fixture_identity(repository)
    core_value = "它把项目身份、关键差异和采用边界绑定到同一组可验证证据，减少阅读完整仓库后才能判断价值的成本。"
    capabilities = copy.deepcopy(_FIXTURE_CAPABILITIES)
    differentiators = copy.deepcopy(_FIXTURE_DIFFERENTIATORS)
    details = [capability["detail"] for capability in capabilities]
    payload.update(
        {
            "officialSummaryZh": identity,
            "identitySummaryZh": identity,
            "coreValueZh": core_value,
            "coreValueEvidenceRefs": ["description"],
            "keyDifferentiators": differentiators,
            "productFormsZh": ["开发工具"],
            "qualityState": "ready",
            "qualityIssues": [],
            "capabilities": capabilities,
            "capabilityBulletsZh": details,
        }
    )


def _apply_v4_detail(payload: dict) -> None:
    repository = payload["project"]["repository"]
    payload["schemaVersion"] = 4
    _apply_v4_profile(payload["project"], repository)
    _apply_v4_profile(payload["profile"], repository)
    payload["profile"]["profileSchemaVersion"] = "rardar-project-profile-v4"
    payload["profile"]["promptVersion"] = "rardar-project-profile-zh-v6"
    payload["profile"]["supportedEnvironmentsZh"] = ["本地开发环境", "持续集成"]
    payload["profile"]["primaryUseCasesZh"] = ["评估开源项目", "复用工程模块"]
    payload["profile"]["deliveryFormsZh"] = ["命令行工具", "结构化报告"]
    payload["profile"]["startHere"] = [
        {
            "label": label,
            "path": path,
            "htmlUrl": f"https://github.com/{repository}/blob/main/{path}",
            "evidenceRefs": ["description"],
        }
        for label, path in [
            ("项目介绍", "README.md"),
            ("快速开始", "docs/quick-start.md"),
            ("核心实现", "src/index.ts"),
            ("架构说明", "docs/architecture.md"),
            ("完整示例", "examples/README.md"),
            ("贡献指南", "CONTRIBUTING.md"),
        ]
    ]
    claims = [
        payload["profile"]["identitySummaryZh"],
        payload["profile"]["coreValueZh"],
        *(item["detail"] for item in payload["profile"]["keyDifferentiators"]),
        *(item["detail"] for item in payload["profile"]["capabilities"]),
    ]
    payload["profile"]["claimEvidenceRefs"].update({claim: ["description"] for claim in claims})


@app.middleware("http")
async def visual_state_fixture(request, call_next):
    """Permit browser tests to exercise UI states without a production-only hook."""
    mode_path = os.environ.get("RARDAR_ADAPTER_TEST_MODE_FILE", "")
    if not mode_path:
        return await call_next(request)
    path = Path(mode_path)
    mode = path.read_text(encoding="utf-8").strip() if path.exists() else "ready"
    if request.url.path.startswith("/api/v1/rardar/projects/") and request.url.path.endswith("/insight"):
        payload = await request.json()
        await asyncio.sleep(0.2)
        github_repository_id = int(request.url.path.split("/")[-2])
        repository = "fixture-lab/exact-1"
        official_intro = {
            "text": "一个经过官方资料约束的开源开发工具。",
            "sourceLabel": "官方介绍（译）",
            "evidenceRefs": ["description"],
        }
        if mode == "ai_error":
            return JSONResponse(
                content={
                    "state": "unavailable",
                    "repository": repository,
                    "githubRepositoryId": github_repository_id,
                    "generationId": payload["generationId"],
                    "promptVersion": "rardar-project-insight-v5",
                    "schemaVersion": "rardar-project-insight-schema-v5",
                    "format": "none",
                    "officialIntro": official_intro,
                    "analysis": None,
                    "errorCode": "rardar_llm_unavailable",
                    "model": None,
                    "provider": None,
                    "cacheHit": False,
                    "evidenceDigest": "a" * 64,
                    "evidenceCacheHit": True,
                    "evidenceKinds": ["description", "readme:introduction", "tree:src"],
                }
            )
        return JSONResponse(
            content={
                "state": "ready",
                "repository": repository,
                "githubRepositoryId": github_repository_id,
                "generationId": payload["generationId"],
                "promptVersion": "rardar-project-insight-v5",
                "schemaVersion": "rardar-project-insight-schema-v5",
                "format": "structured",
                "officialIntro": official_intro,
                "analysis": {
                    "conclusionSummary": {
                        "text": "它把开发自动化能力封装成可组合模块，适合作为工作流的基础组件。",
                        "evidenceRefs": ["description", "readme:introduction"],
                    },
                    "differentiators": [
                        {
                            "text": "相比一次性脚本，可组合模块便于嵌入持续演进的开发工作流。",
                            "evidenceRefs": ["readme:introduction", "tree:src"],
                        }
                    ],
                    "reusableAssets": [
                        {
                            "reuseType": "module_library",
                            "asset": "src 核心模块",
                            "howToUse": "提取模块后接入现有工作流。",
                            "evidenceRefs": ["tree:src"],
                        }
                    ],
                    "reuseCost": {
                        "level": "medium",
                        "reason": "需要从 src 入口适配现有工作流。",
                        "evidenceRefs": ["tree:src"],
                    },
                    "bestFitScenarios": [
                        {"text": "需要组合开发自动化模块的团队。", "evidenceRefs": ["description", "tree:src"]}
                    ],
                    "startHere": [{"label": "核心源码入口", "path": "src", "evidenceRefs": ["tree:src"]}],
                    "implementationBoundaries": [],
                },
                "errorCode": None,
                "model": "mock-rardar-model",
                "provider": "mock",
                "cacheHit": False,
                "evidenceDigest": "a" * 64,
                "evidenceCacheHit": True,
                "evidenceKinds": ["description", "readme:introduction", "tree:src"],
            }
        )
    if request.method == "GET" and request.url.path.startswith("/api/v1/rardar/projects/"):
        github_repository_id = int(request.url.path.rsplit("/", 1)[-1])
        generation_id = request.query_params.get("generationId", "")
        try:
            detail, _etag = load_project_detail(github_repository_id, generation_id)
        except (RardarArtifactError, ServingProjectionError):
            rank = github_repository_id - 10_000
            if mode != "top20" or rank not in range(6, 21):
                return await call_next(request)
            detail, _etag = load_project_detail(1, generation_id)
        payload = detail.model_dump(mode="json")
        if 10_006 <= github_repository_id <= 10_020:
            rank = github_repository_id - 10_000
            repository = _KNOWN_TOP20_REPOSITORIES.get(rank, f"fixture-lab/top-{rank}")
            html_url = f"https://github.com/{repository}"
            payload["project"].update(
                {
                    "rank": rank,
                    "githubRepositoryId": github_repository_id,
                    "repository": repository,
                    "htmlUrl": html_url,
                }
            )
            payload["profile"].update(
                {
                    "githubRepositoryId": github_repository_id,
                    "repository": repository,
                    "htmlUrl": html_url,
                }
            )
            payload["evidence"].update(
                {
                    "githubRepositoryId": github_repository_id,
                    "repository": repository,
                }
            )
        _apply_v4_detail(payload)
        return JSONResponse(content=payload)
    if request.url.path == "/api/v1/rardar/find-projects":
        payload = await request.json()
        repository = (
            "/".join(payload["repositoryUrl"].rstrip("/").split("/")[-2:])
            if payload.get("repositoryUrl")
            else "fixture-owner/project-1"
        )
        names = [
            repository,
            "fixture-owner/project-2",
            "fixture-owner/project-3",
            "fixture-owner/project-4",
            "fixture-owner/project-5",
        ]
        candidates = [
            {
                "githubRepositoryId": 1000 + index,
                "repository": name,
                "description": f"{name} 的真实候选事实摘要。",
                "totalStars": 1000 - index,
                "updatedAt": "2026-08-27T00:00:00Z",
                "primaryLanguage": "Python",
                "licenseSpdxId": "MIT",
                "topics": ["automation", "developer-tools"],
                "htmlUrl": f"https://github.com/{name}",
                "preliminaryMatch": "公开 GitHub 候选与需求关键词相关。",
                "dataState": "github_live",
            }
            for index, name in enumerate(names, 1)
        ]
        comparison = None
        ai_state = "unavailable" if mode == "ai_error" else "ready"
        if ai_state == "ready":
            reuse_types = ["whole_product", "module_library", "reference_only"]
            comparison = {
                "candidates": [
                    {
                        "repository": item["repository"],
                        "whatItDoes": "提供与需求相关的开发能力。",
                        "whyMatched": "仓库事实和需求关键词匹配。",
                        "reusableParts": ["核心模块"],
                        "integrationCost": "medium",
                        "risks": ["需要静态检查"],
                        "recommendation": "先做最小验证。",
                        "reuseType": reuse_types[index],
                    }
                    for index, item in enumerate(candidates[:3])
                ],
                "overallConclusion": "优先验证前三个真实候选。",
            }
        return JSONResponse(
            content={
                "requirement": payload["requirement"],
                "repositoryUrl": payload.get("repositoryUrl"),
                "searchState": "github_live",
                "coverageLabel": "来自公开 GitHub Search 的有限候选集；Rardar 没有扫描全部 GitHub。",
                "sources": ["GitHub Search"],
                "quickCandidates": candidates,
                "aiState": ai_state,
                "comparison": comparison,
                "plainComparison": None,
                "errorCode": "rardar_llm_unavailable" if ai_state == "unavailable" else None,
                "promptVersion": "rardar-find-project-v1",
                "model": "mock-rardar-model" if ai_state == "ready" else None,
                "provider": "mock" if ai_state == "ready" else None,
                "cacheHit": False,
            }
        )
    if request.url.path not in {"/api/v1/rardar/explosion-board", "/api/v1/rardar/today"}:
        return await call_next(request)
    if mode == "top20" and request.url.path == "/api/v1/rardar/today":
        try:
            payload = load_today_snapshot()[0].model_dump(mode="json")
        except RardarArtifactError as exc:
            return JSONResponse(status_code=503, content={"detail": {"code": exc.code, "message": str(exc)}})
        template = payload["exactRanked"][0]
        for index in range(len(payload["exactRanked"]) + 1, 21):
            item = copy.deepcopy(template)
            item.update(
                {
                    "rank": index,
                    "githubRepositoryId": 10_000 + index,
                    "repository": f"fixture-lab/top-{index}",
                    "htmlUrl": f"https://github.com/fixture-lab/top-{index}",
                    "observedStarDelta": 1000 - index,
                }
            )
            payload["exactRanked"].append(item)
        payload["schemaVersion"] = 4
        for item in payload["exactRanked"]:
            repository = _KNOWN_TOP20_REPOSITORIES.get(item["rank"], item["repository"])
            item["repository"] = repository
            item["htmlUrl"] = f"https://github.com/{repository}"
            _apply_v4_profile(item, repository)
        profile_states = [item["profileState"] for item in payload["exactRanked"]]
        payload["profileSummary"] = {
            "total": 20,
            "complete": profile_states.count("complete"),
            "partial": profile_states.count("partial"),
            "sourceUnavailable": profile_states.count("source_unavailable"),
            "chineseSummaries": 20,
            "qualityReady": 20,
            "qualityPartial": 0,
            "qualityRejected": 0,
        }
        payload["coverage"]["exactCount"] = 20
        return JSONResponse(content=payload)
    if mode in {"ready", "ai_error"}:
        return await call_next(request)
    if mode == "error":
        return JSONResponse(
            status_code=503,
            content={"detail": {"code": "rardar_generation_invalid", "message": "visual negative control"}},
        )
    if mode == "not_configured":
        if request.url.path == "/api/v1/rardar/today":
            return JSONResponse(status_code=503, content={"detail": {"code": "rardar_serving_unavailable"}})
        return JSONResponse(
            content={
                "state": "not_synced",
                "reason": "real_data_not_synced",
                "generationId": None,
                "publishedAt": None,
                "capturedAt": None,
                "window": None,
                "coverage": None,
                "exactRanked": [],
                "pendingRanked": [],
                "conflictCount": 0,
                "sourceStatus": None,
                "dataMode": "real",
                "dataLabel": "真实数据尚未同步",
                "syncedAt": None,
                "sourceHost": None,
                "manifestSha256": None,
                "artifactSha256": None,
            }
        )
    if mode in {"warming_up", "baseline_missing"}:
        try:
            payload = (
                load_today_snapshot()[0].model_dump(mode="json")
                if request.url.path == "/api/v1/rardar/today"
                else load_explosion_board().model_dump(mode="json")
            )
        except RardarArtifactError as exc:
            return JSONResponse(status_code=503, content={"detail": {"code": exc.code, "message": str(exc)}})
        payload["state"] = mode
        payload["window"]["state"] = mode
        payload["exactRanked"] = []
        payload["coverage"]["exactCount"] = 0
        if "profileSummary" in payload:
            payload["profileSummary"] = {
                "total": 0,
                "complete": 0,
                "partial": 0,
                "sourceUnavailable": 0,
                "chineseSummaries": 0,
            }
        return JSONResponse(content=payload)
    return JSONResponse(status_code=500, content={"detail": {"code": "invalid_test_mode"}})
