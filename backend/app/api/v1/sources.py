from __future__ import annotations
from typing import Optional
import xml.etree.ElementTree as ET

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime

from app.database import get_db
from app.models.source import Source, SourceType, SourceStatus
from app.schemas.source import (
    SourceCreate, SourceUpdate, SourceResponse, SourceListResponse,
    SyncResultResponse,
)
from app.services.content_pipeline import ingest_from_source

router = APIRouter(prefix="/sources", tags=["sources"])


@router.post("", response_model=SourceResponse, status_code=201)
async def create_source(data: SourceCreate, db: AsyncSession = Depends(get_db)):
    source = Source(**data.model_dump())
    db.add(source)
    await db.flush()
    await db.refresh(source)
    return source


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
    query = select(Source)
    count_query = select(func.count()).select_from(Source)

    if source_type:
        query = query.where(Source.source_type == source_type)
        count_query = count_query.where(Source.source_type == source_type)
    if status:
        query = query.where(Source.status == status)
        count_query = count_query.where(Source.status == status)
    if enabled is not None:
        query = query.where(Source.enabled == enabled)
        count_query = count_query.where(Source.enabled == enabled)
    if keyword:
        query = query.where(Source.name.ilike(f"%{keyword}%"))
        count_query = count_query.where(Source.name.ilike(f"%{keyword}%"))

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    query = query.order_by(Source.created_at.desc()).offset(offset).limit(page_size)

    result = await db.execute(query)
    items = result.scalars().all()

    return SourceListResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("/import-opml")
async def import_opml(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Import RSS feeds from OPML file (e.g., exported from Folo/Follow).
    Extracts all <outline xmlUrl="..."> entries and creates Source records.
    """
    content = await file.read()

    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        raise HTTPException(status_code=400, detail="Invalid OPML XML")

    # OPML body contains outline elements
    body = root.find("body")
    if body is None:
        raise HTTPException(status_code=400, detail="No <body> element found in OPML")

    outlines = body.findall(".//outline[@xmlUrl]")

    created = 0
    skipped = 0

    for outline in outlines:
        feed_url = outline.get("xmlUrl", "").strip()
        if not feed_url:
            continue

        # Skip duplicates by URL
        existing = await db.execute(select(Source).where(Source.url == feed_url))
        if existing.scalar_one_or_none():
            skipped += 1
            continue

        name = outline.get("title") or outline.get("text") or feed_url

        source = Source(
            name=name,
            url=feed_url,
            source_type=SourceType.RSS,
            category="导入",
            enabled=True,
            status=SourceStatus.ACTIVE,
        )
        db.add(source)
        await db.flush()
        created += 1

    return {
        "created": created,
        "skipped": skipped,
        "total": len(outlines),
        "message": f"成功导入 {created} 个源，跳过 {skipped} 个重复。",
    }


@router.get("/{source_id}", response_model=SourceResponse)
async def get_source(source_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Source).where(Source.id == source_id))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    return source


@router.put("/{source_id}", response_model=SourceResponse)
async def update_source(
    source_id: int, data: SourceUpdate, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Source).where(Source.id == source_id))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(source, key, value)
    source.updated_at = datetime.utcnow()
    await db.flush()
    await db.refresh(source)
    return source


@router.delete("/{source_id}", status_code=204)
async def delete_source(source_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Source).where(Source.id == source_id))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    await db.delete(source)
    await db.flush()


@router.post("/{source_id}/sync", response_model=SyncResultResponse)
async def sync_source(source_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Source).where(Source.id == source_id))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    stats = await ingest_from_source(source, db)
    await db.refresh(source)

    return SyncResultResponse(
        fetched=stats["fetched"],
        new=stats["new"],
        duplicates=stats["duplicates"],
        source_info=SourceResponse.model_validate(source),
    )
