"""
App-level settings API — RSSHub instance management.
"""

from __future__ import annotations
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.app_setting import AppSetting

router = APIRouter(prefix="/settings", tags=["settings"])


class RSSHubInstanceItem(BaseModel):
    url: str
    enabled: bool = True
    priority: int = 0
    note: str = ""


class RSSHubInstancesGetResponse(BaseModel):
    instances: list[RSSHubInstanceItem]
    default_instances: list[str]


class RSSHubInstancesUpdateRequest(BaseModel):
    instances: list[RSSHubInstanceItem]


@router.get("/rsshub/instances", response_model=RSSHubInstancesGetResponse)
async def get_rsshub_instances(db: AsyncSession = Depends(get_db)):
    """Get current RSSHub instance list (from DB or defaults)."""
    result = await db.execute(
        select(AppSetting).where(AppSetting.key == "rsshub_instances")
    )
    row = result.scalar_one_or_none()

    if row and row.value:
        try:
            raw = json.loads(row.value)
            instances = [RSSHubInstanceItem(**item) for item in raw]
        except (json.JSONDecodeError, Exception):
            instances = []
    else:
        instances = []

    from app.models.app_setting import DEFAULT_RSSHUB_INSTANCES
    return {
        "instances": instances,
        "default_instances": [i["url"] for i in DEFAULT_RSSHUB_INSTANCES],
    }


@router.put("/rsshub/instances")
async def update_rsshub_instances(
    req: RSSHubInstancesUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update RSSHub instance list. Supports enable/disable/add/remove."""
    # Validate URLs
    for inst in req.instances:
        if not inst.url.startswith("http://") and not inst.url.startswith("https://"):
            raise HTTPException(status_code=400, detail=f"Invalid URL: {inst.url}")

    raw_value = json.dumps([inst.model_dump() for inst in req.instances], ensure_ascii=False)

    result = await db.execute(
        select(AppSetting).where(AppSetting.key == "rsshub_instances")
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.value = raw_value
        existing.updated_at = datetime.utcnow()
    else:
        db.add(AppSetting(
            key="rsshub_instances",
            value=raw_value,
            description="RSSHub 实例列表，支持多实例降级",
            updated_at=datetime.utcnow(),
        ))

    await db.commit()

    return {"instances": req.instances, "updated": True}


# ── DuckDB analytics layer management ──

@router.get("/duckdb/status")
async def duckdb_status():
    """Get DuckDB analytical layer status.

    The current architecture uses DuckDB in-memory with SQLite ATTACH (READ_ONLY).
    No sync step is needed — DuckDB queries always see fresh SQLite data.
    """
    try:
        from app.services.duckdb_service import get_analytics
        analytics = get_analytics()
        available = analytics.available
        return {
            "status": "ok" if available else "unavailable",
            "architecture": "in-memory DuckDB + SQLite ATTACH (READ_ONLY)",
            "note": "No sync needed — DuckDB reads SQLite directly." if available
                    else "DuckDB or sqlite extension not installed. App falls back to SQLAlchemy.",
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
