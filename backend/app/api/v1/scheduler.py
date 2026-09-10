"""
Scheduled Jobs & Execution Logs API endpoints.
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.auth import get_current_admin_user
from app.core.config import settings
from app.services.job_tracker import get_all_job_configs, get_recent_logs

router = APIRouter(prefix="/scheduler", tags=["scheduler"], dependencies=[Depends(get_current_admin_user)])
logger = logging.getLogger(__name__)


class DailyBudgetConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    providerRequestLimit: int = Field(strict=True, ge=1, le=100_000)
    interactiveReserve: int | None = Field(default=None, strict=True, ge=0, le=100_000)
    earlyBackgroundLimit: int | None = Field(default=None, strict=True, ge=0, le=100_000)


def _require_same_origin(request: Request) -> None:
    if not request.headers.get("authorization", "").lower().startswith("bearer ") and (
        request.headers.get("origin") not in settings.cors_origins
        or request.headers.get("sec-fetch-site") == "cross-site"
    ):
        raise HTTPException(status_code=403, detail="scheduler_origin_rejected")


@router.get("/rardar-daily-config")
async def get_daily_config():
    from app.services.job_tracker import daily_config_status

    return await daily_config_status()


@router.post("/rardar-daily-config")
async def save_daily_config(body: DailyBudgetConfig, request: Request):
    from app.services.job_tracker import daily_config_status

    _require_same_origin(request)
    try:
        return await daily_config_status(
            body.providerRequestLimit,
            interactive_reserve=body.interactiveReserve,
            early_background_limit=body.earlyBackgroundLimit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.post("/jobs/rardar_daily_operations/{action}")
async def control_daily_job(action: Literal["pause", "resume", "run"], request: Request):
    from app.services.job_tracker import control_rardar_daily_job

    _require_same_origin(request)
    try:
        return await control_rardar_daily_job(action)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@router.get("/jobs")
async def list_jobs():
    """List all scheduled job configurations with last run info."""
    jobs = await get_all_job_configs()
    return {"jobs": jobs, "total": len(jobs)}


@router.get("/logs")
async def list_logs(
    job_key: str = Query(None, description="Filter by job_key"),
    limit: int = Query(50, ge=1, le=200, description="Max records"),
):
    """List recent job execution logs."""
    logs = await get_recent_logs(job_key=job_key or "", limit=limit)
    return {"logs": logs, "total": len(logs)}
