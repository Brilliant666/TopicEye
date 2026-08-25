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
    if request.url.path != "/api/v1/rardar/explosion-board" or not mode_path:
        return await call_next(request)
    path = Path(mode_path)
    mode = path.read_text(encoding="utf-8").strip() if path.exists() else "ready"
    if mode == "ready":
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
