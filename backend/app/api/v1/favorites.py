from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.models.favorite import FavoriteStatus, FavoriteTargetType
from app.repositories.favorite_repo import FavoriteRepo
from app.schemas.favorite import FavoriteCreate, FavoriteListResponse, FavoriteResponse, FavoriteUpdate

router = APIRouter(prefix="/favorites", tags=["favorites"])


@router.get("", response_model=FavoriteListResponse)
async def list_favorites(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    target_type: Optional[FavoriteTargetType] = None,
    status: Optional[FavoriteStatus] = None,
    keyword: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    items, total = await FavoriteRepo(db).list_paginated(
        page=page,
        page_size=page_size,
        target_type=target_type,
        status=status,
        keyword=keyword,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("", response_model=FavoriteResponse, status_code=201)
async def create_favorite(
    data: FavoriteCreate,
    db: AsyncSession = Depends(get_db),
):
    repo = FavoriteRepo(db)
    try:
        return await repo.upsert(data)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/state")
async def favorite_state(
    target_type: FavoriteTargetType,
    target_ids: Optional[str] = Query(None, description="Comma-separated target IDs"),
    target_keys: Optional[str] = Query(None, description="Comma-separated target keys"),
    db: AsyncSession = Depends(get_db),
):
    ids = [int(item) for item in target_ids.split(",") if item.strip()] if target_ids else None
    keys = [item.strip() for item in target_keys.split(",") if item.strip()] if target_keys else None
    return {
        "items": await FavoriteRepo(db).state_for_targets(
            target_type,
            target_ids=ids,
            target_keys=keys,
        )
    }


@router.patch("/{favorite_id}", response_model=FavoriteResponse)
async def update_favorite(
    favorite_id: int,
    data: FavoriteUpdate,
    db: AsyncSession = Depends(get_db),
):
    item = await FavoriteRepo(db).update(favorite_id, data)
    if not item:
        raise HTTPException(status_code=404, detail="Favorite not found")
    return item


@router.delete("/{favorite_id}")
async def delete_favorite(
    favorite_id: int,
    db: AsyncSession = Depends(get_db),
):
    deleted = await FavoriteRepo(db).delete(favorite_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Favorite not found")
    return {"deleted": True}
