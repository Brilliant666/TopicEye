"""Minimal process-level host for Adapter HTTP/UI tests; no database lifespan."""

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.api.v1.rardar import router
from app.integrations.rardar import RardarArtifactError
from app.services.rardar_intelligence import load_explosion_board, load_today_snapshot

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
    if request.url.path.startswith("/api/v1/rardar/projects/") and request.url.path.endswith("/insight"):
        payload = await request.json()
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
                    "promptVersion": "rardar-project-insight-v2",
                    "schemaVersion": "rardar-project-insight-schema-v2",
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
                "promptVersion": "rardar-project-insight-v2",
                "schemaVersion": "rardar-project-insight-schema-v2",
                "format": "structured",
                "officialIntro": official_intro,
                "analysis": {
                    "officialIntro": official_intro,
                    "coreHighlights": [
                        {"text": "提供可组合的开发自动化能力。", "evidenceRefs": ["readme:introduction"]}
                    ],
                    "reusableAssets": [
                        {
                            "reuseType": "module_library",
                            "asset": "src 核心模块",
                            "howToUse": "提取模块后接入现有工作流。",
                            "evidenceRefs": ["tree:src"],
                        }
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
