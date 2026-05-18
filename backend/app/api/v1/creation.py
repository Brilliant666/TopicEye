"""
Creation plan API endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.services.creation import generate_creation_plan, PLATFORM_PROMPTS

router = APIRouter(prefix="/creation", tags=["creation"])


class CreationRequest(BaseModel):
    content_id: int
    platform: str  # xiaohongshu / short_video / wechat


async def get_db():
    async with async_session() as db:
        yield db


@router.post("/plan")
async def create_plan(req: CreationRequest, db: AsyncSession = Depends(get_db)):
    """Generate a creation plan for a content item on a specific platform."""
    if req.platform not in PLATFORM_PROMPTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported platform: {req.platform}. Supported: {list(PLATFORM_PROMPTS.keys())}"
        )
    result = await generate_creation_plan(db, req.content_id, req.platform)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/platforms")
async def list_platforms():
    """List available creation platforms."""
    return {
        "platforms": [
            {"id": k, "name": v["name"]}
            for k, v in PLATFORM_PROMPTS.items()
        ]
    }
