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

@router.post("/duckdb/sync")
async def trigger_duckdb_sync():
    """Manually trigger a full sync from SQLite to DuckDB analytical layer."""
    try:
        from app.services.duckdb_service import sync_full
        stats = sync_full()
        return {"status": "ok", "synced": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DuckDB sync failed: {e}")


@router.get("/duckdb/status")
async def duckdb_status():
    """Get DuckDB analytical layer status — table counts and last sync time."""
    try:
        from app.database import get_duckdb_conn
        conn = get_duckdb_conn()

        content_count = conn.execute("SELECT COUNT(*) FROM analytics_content").fetchone()[0]
        topics_count = conn.execute("SELECT COUNT(*) FROM analytics_topics").fetchone()[0]
        trends_count = conn.execute("SELECT COUNT(*) FROM analytics_trends").fetchone()[0]

        watermark = conn.execute(
            "SELECT last_synced_at FROM _sync_watermark WHERE table_name = 'analytics_content'"
        ).fetchone()
        last_sync = str(watermark[0]) if watermark else None

        return {
            "status": "ok",
            "tables": {
                "analytics_content": content_count,
                "analytics_topics": topics_count,
                "analytics_trends": trends_count,
            },
            "last_synced_at": last_sync,
        }
    except Exception as e:
        return {"status": "not_initialized", "error": str(e)}
