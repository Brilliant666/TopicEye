"""Minimal process-level host for Adapter HTTP/UI tests; no database lifespan."""

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.api.v1.rardar import router
from app.integrations.rardar import RardarArtifactError
from app.services.rardar_intelligence import load_explosion_board

app = FastAPI()
app.include_router(router, prefix="/api/v1")


@app.middleware("http")
async def visual_state_fixture(request, call_next):
    """Permit browser tests to exercise UI states without a production-only hook."""
    mode_path = os.environ.get("RARDAR_ADAPTER_TEST_MODE_FILE", "")
    if not mode_path:
        return await call_next(request)
    path = Path(mode_path)
    mode = path.read_text(encoding="utf-8").strip() if path.exists() else "ready"
    if request.url.path == "/api/v1/rardar/projects/explain":
        payload = await request.json()
        if mode == "ai_error":
            return JSONResponse(
                content={
                    "state": "unavailable",
                    "repository": payload["repository"],
                    "generationId": payload["generationId"],
                    "promptVersion": "rardar-project-explanation-v1",
                    "format": "none",
                    "analysis": None,
                    "plainText": None,
                    "errorCode": "rardar_llm_unavailable",
                    "model": None,
                    "provider": None,
                    "cacheHit": False,
                }
            )
        return JSONResponse(
            content={
                "state": "ready",
                "repository": payload["repository"],
                "generationId": payload["generationId"],
                "promptVersion": "rardar-project-explanation-v1",
                "format": "structured",
                "analysis": {
                    "summaryZh": "一个经过事实约束的开源项目。",
                    "whyWorthWatching": "它在当前观测窗口内获得了较多新增关注。",
                    "reuseIdeas": ["先验证核心模块，再做最小集成"],
                    "risks": ["许可证和接口稳定性仍需核对"],
                },
                "plainText": None,
                "errorCode": None,
                "model": "mock-rardar-model",
                "provider": "mock",
                "cacheHit": False,
            }
        )
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
    if request.url.path != "/api/v1/rardar/explosion-board":
        return await call_next(request)
    if mode in {"ready", "ai_error"}:
        return await call_next(request)
    if mode == "error":
        return JSONResponse(
            status_code=503,
            content={"detail": {"code": "rardar_generation_invalid", "message": "visual negative control"}},
        )
    if mode == "not_configured":
        return JSONResponse(
            status_code=503,
            content={"detail": {"code": "rardar_intelligence_not_configured", "message": "visual state"}},
        )
    if mode in {"warming_up", "baseline_missing"}:
        try:
            payload = load_explosion_board().model_dump(mode="json")
        except RardarArtifactError as exc:
            return JSONResponse(status_code=503, content={"detail": {"code": exc.code, "message": str(exc)}})
        payload["state"] = mode
        payload["window"]["state"] = mode
        payload["exactRanked"] = []
        payload["coverage"]["exactCount"] = 0
        return JSONResponse(content=payload)
    return JSONResponse(status_code=500, content={"detail": {"code": "invalid_test_mode"}})
