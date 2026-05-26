from __future__ import annotations
from typing import Optional
import json
import re
import xml.etree.ElementTree as ET

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.exceptions import NotFoundError
from app.models.source import Source, SourceType, SourceStatus
from app.schemas.source import (
    SourceCreate, SourceUpdate, SourceResponse, SourceListResponse,
    SyncResultResponse,
)
from app.repositories.source_repo import SourceRepository
from app.services.content_pipeline import ingest_from_source

router = APIRouter(prefix="/sources", tags=["sources"])


@router.post("", response_model=SourceResponse, status_code=201)
async def create_source(data: SourceCreate, db: AsyncSession = Depends(get_db)):
    repo = SourceRepository(db)
    return await repo.create(**data.model_dump())


@router.get("", response_model=SourceListResponse)
async def list_sources(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    source_type: Optional[str] = None,
    status: Optional[str] = None,
    enabled: Optional[bool] = None,
    keyword: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    repo = SourceRepository(db)
    filters = {
        "source_type": source_type,
        "status": status,
        "enabled": enabled,
    }
    if keyword:
        filters["name"] = f"%{keyword}%"

    items, total = await repo.list_paginated(
        page=page, page_size=page_size,
        filters={k: v for k, v in filters.items() if v is not None},
        sort_by="created_at", sort_order="desc",
    )
    return SourceListResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("/import-opml")
async def import_opml(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Import RSS feeds from OPML file."""
    content = await file.read()
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        raise HTTPException(status_code=400, detail="Invalid OPML XML")

    body = root.find("body")
    if body is None:
        raise HTTPException(status_code=400, detail="No <body> element found in OPML")

    outlines = body.findall(".//outline[@xmlUrl]")
    repo = SourceRepository(db)
    created = skipped = 0

    for outline in outlines:
        feed_url = outline.get("xmlUrl", "").strip()
        if not feed_url:
            continue
        existing = await repo.get_one(Source.url == feed_url)
        if existing:
            skipped += 1
            continue

        name = outline.get("title") or outline.get("text") or feed_url

        # Detect xgo.ing Twitter RSS feeds
        if "xgo.ing" in feed_url:
            source_type = SourceType.TWITTER_RSS
            # Extract @handle from name like "OpenAI(@OpenAI)"
            screen_name = ""
            handle_match = re.search(r'\(@?(\w+)\)', name)
            if handle_match:
                screen_name = handle_match.group(1)
            keyword = json.dumps({"screen_name": screen_name}) if screen_name else None
        else:
            source_type = SourceType.RSS
            keyword = None

        await repo.create(
            name=name, url=feed_url,
            source_type=source_type, category="导入",
            enabled=True, status=SourceStatus.ACTIVE,
            keyword=keyword,
        )
        created += 1

    return {
        "created": created, "skipped": skipped, "total": len(outlines),
        "message": f"成功导入 {created} 个源，跳过 {skipped} 个重复。",
    }


@router.get("/{source_id}", response_model=SourceResponse)
async def get_source(source_id: int, db: AsyncSession = Depends(get_db)):
    repo = SourceRepository(db)
    try:
        return await repo.get_by_id_or_raise(source_id, resource_name="Source")
    except NotFoundError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.put("/{source_id}", response_model=SourceResponse)
async def update_source(
    source_id: int, data: SourceUpdate, db: AsyncSession = Depends(get_db)
):
    repo = SourceRepository(db)
    try:
        return await repo.update(source_id, **data.model_dump(exclude_unset=True))
    except NotFoundError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.delete("/{source_id}", status_code=204)
async def delete_source(source_id: int, db: AsyncSession = Depends(get_db)):
    repo = SourceRepository(db)
    try:
        await repo.delete(source_id)
    except NotFoundError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/{source_id}/sync", response_model=SyncResultResponse)
async def sync_source(source_id: int, db: AsyncSession = Depends(get_db)):
    repo = SourceRepository(db)
    try:
        source = await repo.get_by_id_or_raise(source_id, resource_name="Source")
    except NotFoundError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

    stats = await ingest_from_source(source, db)
    await db.refresh(source)
    return SyncResultResponse(
        fetched=stats["fetched"], new=stats["new"], duplicates=stats["duplicates"],
        source_info=SourceResponse.model_validate(source),
    )
