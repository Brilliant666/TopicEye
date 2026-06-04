from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session
from app.core.dependencies import get_db
from app.models.favorite import FavoriteStatus, FavoriteTargetType
from app.repositories.favorite_repo import FavoriteRepo
from app.schemas.favorite import (
    FavoriteBulkDeleteRequest,
    FavoriteBulkStatusRequest,
    FavoriteCreate,
    FavoriteListResponse,
    FavoriteReorderRequest,
    FavoriteResponse,
    FavoriteUpdate,
)
from app.services.content_read_cache import invalidate_content_read_caches
from app.services.favorite_cache import (
    favorite_to_dict,
    get_cached_json,
    invalidate_favorite_cache,
    set_cached_json,
)
from app.services.json_cache import invalidate_json_cache

router = APIRouter(prefix="/favorites", tags=["favorites"])


def _invalidate_favorite_mutation_caches(*, content_changed: bool = False) -> None:
    invalidate_favorite_cache()
    invalidate_json_cache("contents:favorites:")
    if content_changed:
        invalidate_content_read_caches()


def _favorite_cache_hit_response(content: bytes, age_seconds: float) -> Response:
    return Response(
        content=content,
        media_type="application/json",
        headers={
            "X-Favorites-Cache": "HIT",
            "X-Favorites-Cache-Age-Ms": str(round(age_seconds * 1000, 3)),
        },
    )


@router.get("", response_model=FavoriteListResponse)
async def list_favorites(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    target_type: Optional[FavoriteTargetType] = None,
    status: Optional[FavoriteStatus] = None,
    keyword: Optional[str] = None,
):
    cache_key = f"list:{page}:{page_size}:{target_type or ''}:{status or ''}:{keyword or ''}"
    cached = get_cached_json(cache_key)
    if cached:
        content, age_seconds = cached
        return _favorite_cache_hit_response(content, age_seconds)

    async with async_session() as db:
        items, total = await FavoriteRepo(db).list_paginated(
            page=page,
            page_size=page_size,
            target_type=target_type,
            status=status,
            keyword=keyword,
        )
    payload = {
        "items": [favorite_to_dict(item) for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
    content = set_cached_json(cache_key, payload)
    return Response(
        content=content,
        media_type="application/json",
        headers={"X-Favorites-Cache": "MISS"},
    )


@router.post("", response_model=FavoriteResponse, status_code=201)
async def create_favorite(
    data: FavoriteCreate,
    db: AsyncSession = Depends(get_db),
):
    repo = FavoriteRepo(db)
    try:
        item = await repo.upsert(data)
        _invalidate_favorite_mutation_caches(content_changed=data.target_type == FavoriteTargetType.CONTENT)
        return item
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/state")
async def favorite_state(
    target_type: FavoriteTargetType,
    target_ids: Optional[str] = Query(None, description="Comma-separated target IDs"),
    target_keys: Optional[str] = Query(None, description="Comma-separated target keys"),
):
    cache_key = f"state:{target_type}:{target_ids or ''}:{target_keys or ''}"
    cached = get_cached_json(cache_key)
    if cached:
        content, age_seconds = cached
        return _favorite_cache_hit_response(content, age_seconds)

    try:
        ids = [int(item) for item in target_ids.split(",") if item.strip()] if target_ids else None
    except ValueError:
        raise HTTPException(status_code=422, detail="target_ids must be comma-separated integers")
    keys = [item.strip() for item in target_keys.split(",") if item.strip()] if target_keys else None
    async with async_session() as db:
        state_items = await FavoriteRepo(db).state_for_targets(
            target_type,
            target_ids=ids,
            target_keys=keys,
        )
    payload = {"items": state_items}
    content = set_cached_json(cache_key, payload)
    return Response(
        content=content,
        media_type="application/json",
        headers={"X-Favorites-Cache": "MISS"},
    )


@router.post("/reorder", response_model=list[FavoriteResponse])
async def reorder_favorites(
    data: FavoriteReorderRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        items = await FavoriteRepo(db).reorder_status(status=data.status, ordered_ids=data.ordered_ids)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    _invalidate_favorite_mutation_caches()
    return items


@router.post("/bulk-status", response_model=list[FavoriteResponse])
async def bulk_update_favorite_status(
    data: FavoriteBulkStatusRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        items = await FavoriteRepo(db).bulk_update_status(status=data.status, ids=data.ids)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    _invalidate_favorite_mutation_caches()
    return items


@router.post("/bulk-delete")
async def bulk_delete_favorites(
    data: FavoriteBulkDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    repo = FavoriteRepo(db)
    content_changed = False
    for favorite_id in data.ids:
        item = await repo.get_by_id(favorite_id)
        if item is not None and item.target_type == FavoriteTargetType.CONTENT:
            content_changed = True
            break
    try:
        deleted = await repo.bulk_delete(data.ids)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    _invalidate_favorite_mutation_caches(content_changed=content_changed)
    return {"deleted": deleted}


@router.patch("/{favorite_id}", response_model=FavoriteResponse)
async def update_favorite(
    favorite_id: int,
    data: FavoriteUpdate,
    db: AsyncSession = Depends(get_db),
):
    item = await FavoriteRepo(db).update(favorite_id, data)
    if not item:
        raise HTTPException(status_code=404, detail="Favorite not found")
    _invalidate_favorite_mutation_caches()
    return item


@router.delete("/{favorite_id}")
async def delete_favorite(
    favorite_id: int,
    db: AsyncSession = Depends(get_db),
):
    repo = FavoriteRepo(db)
    item = await repo.get_by_id(favorite_id)
    deleted = await repo.delete(favorite_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Favorite not found")
    _invalidate_favorite_mutation_caches(
        content_changed=item is not None and item.target_type == FavoriteTargetType.CONTENT
    )
    return {"deleted": True}
