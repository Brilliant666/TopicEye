from __future__ import annotations
from typing import Any, Optional
import json
import re
import xml.etree.ElementTree as ET

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.database import async_session
from app.core.dependencies import get_db
from app.core.exceptions import NotFoundError
from app.models.source import Source, SourceType, SourceStatus
from app.schemas.source import (
    SourceCreate, SourceUpdate, SourceResponse, SourceListResponse,
    SourceReorderRequest, SyncResultResponse,
    normalize_source_url_value,
)
from app.repositories.source_repo import SourceRepository
from app.services.content_pipeline import ingest_from_source
from app.services.source_cache import (
    SourceListCacheParams,
    get_cached_source_list,
    invalidate_source_list_cache,
    set_cached_source_list,
)

router = APIRouter(prefix="/sources", tags=["sources"])


def _invalidate_source_cache() -> None:
    invalidate_source_list_cache()


class SourceBatchImportRequest(BaseModel):
    content: str = Field(..., min_length=1)
    category: str = "批量导入"
    enabled: bool = True
    weight: int = Field(default=3, ge=1, le=5)


class SourceBatchImportItem(BaseModel):
    name: str
    url: str
    source_type: str
    category: str
    platform: Optional[str] = None
    duplicate: bool = False


def _guess_source_type(url: str) -> SourceType:
    lower = url.lower()
    if "/api/" in lower or lower.endswith(".json"):
        return SourceType.API
    if "xgo.ing" in lower or "twitter.com" in lower or "x.com/" in lower:
        return SourceType.TWITTER_RSS if "xgo.ing" in lower else SourceType.X
    if "rsshub" in lower:
        return SourceType.RSSHub
    if "reddit.com" in lower:
        return SourceType.REDDIT
    if "youtube.com" in lower or "youtu.be" in lower:
        return SourceType.YOUTUBE
    if "zhihu.com" in lower:
        return SourceType.ZHIHU
    if "/feed" in lower or lower.endswith((".xml", ".rss", ".atom")) or "rss" in lower:
        return SourceType.RSS
    return SourceType.WEBSITE


def _guess_platform(url: str) -> Optional[str]:
    lower = url.lower()
    if "github.com" in lower:
        return "GitHub"
    if "x.com" in lower or "twitter.com" in lower or "xgo.ing" in lower:
        return "X"
    if "reddit.com" in lower:
        return "Reddit"
    if "youtube.com" in lower or "youtu.be" in lower:
        return "YouTube"
    if "zhihu.com" in lower:
        return "知乎"
    if "rsshub" in lower:
        return "RSSHub"
    return None


def _as_source_item(raw: Any, default_category: str) -> Optional[dict]:
    if not isinstance(raw, dict):
        return None
    url = (
        raw.get("url")
        or raw.get("feed")
        or raw.get("rss")
        or raw.get("rss_url")
        or raw.get("feedUrl")
        or raw.get("feed_url")
        or raw.get("xmlUrl")
        or raw.get("href")
    )
    if not isinstance(url, str):
        return None
    try:
        normalized_url = normalize_source_url_value(url)
    except ValueError:
        return None
    name = (
        raw.get("name")
        or raw.get("title")
        or raw.get("label")
        or raw.get("site")
        or raw.get("source")
        or normalized_url
    )
    category = raw.get("category") or raw.get("group") or raw.get("type") or default_category
    source_type = raw.get("source_type") or raw.get("sourceType")
    try:
        parsed_type = SourceType(source_type) if source_type else _guess_source_type(normalized_url)
    except ValueError:
        parsed_type = _guess_source_type(normalized_url)
    return {
        "name": str(name).strip()[:255] or normalized_url,
        "url": normalized_url,
        "source_type": parsed_type,
        "category": str(category).strip()[:100] or default_category,
        "platform": raw.get("platform") or _guess_platform(normalized_url),
    }


def _walk_json_sources(value: Any, default_category: str) -> list[dict]:
    found: list[dict] = []
    item = _as_source_item(value, default_category)
    if item:
        found.append(item)
    if isinstance(value, dict):
        for child in value.values():
            found.extend(_walk_json_sources(child, default_category))
    elif isinstance(value, list):
        for child in value:
            found.extend(_walk_json_sources(child, default_category))
    return found


def _parse_source_batch(content: str, default_category: str) -> list[dict]:
    text = content.strip()
    sources: list[dict] = []

    if text.startswith("<"):
        try:
            root = ET.fromstring(text.encode())
            for outline in root.findall(".//outline[@xmlUrl]"):
                try:
                    url = normalize_source_url_value(outline.get("xmlUrl", ""))
                except ValueError:
                    continue
                sources.append({
                    "name": (outline.get("title") or outline.get("text") or url).strip()[:255],
                    "url": url,
                    "source_type": _guess_source_type(url),
                    "category": outline.get("category") or default_category,
                    "platform": _guess_platform(url),
                })
        except ET.ParseError:
            pass

    try:
        parsed = json.loads(text)
        sources.extend(_walk_json_sources(parsed, default_category))
    except json.JSONDecodeError:
        pass

    markdown_link_re = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", re.IGNORECASE)
    for name, url in markdown_link_re.findall(text):
        url = normalize_source_url_value(url)
        sources.append({
            "name": name.strip()[:255],
            "url": url,
            "source_type": _guess_source_type(url),
            "category": default_category,
            "platform": _guess_platform(url),
        })

    line_url_re = re.compile(r"(?P<url>https?://[^\s)\]\"']+)", re.IGNORECASE)
    for line in text.splitlines():
        clean_line = line.strip(" -\t")
        match = line_url_re.search(clean_line)
        if not match:
            continue
        raw_url = match.group("url").rstrip(".,;")
        url = normalize_source_url_value(raw_url)
        name = clean_line.replace(raw_url, "").strip(" :-—|") or url
        sources.append({
            "name": name[:255],
            "url": url,
            "source_type": _guess_source_type(url),
            "category": default_category,
            "platform": _guess_platform(url),
        })

    deduped: dict[str, dict] = {}
    for item in sources:
        url = item["url"].strip()
        if url and url not in deduped:
            deduped[url] = item
    return list(deduped.values())


async def _preview_source_batch_items(db: AsyncSession, content: str, category: str) -> list[SourceBatchImportItem]:
    parsed = _parse_source_batch(content, category)
    if not parsed:
        return []
    urls = [item["url"] for item in parsed]
    existing_result = await db.execute(select(Source.url).where(Source.url.in_(urls)))
    existing_urls = set(existing_result.scalars().all())
    return [
        SourceBatchImportItem(
            name=item["name"],
            url=item["url"],
            source_type=item["source_type"].value,
            category=item["category"],
            platform=item.get("platform"),
            duplicate=item["url"] in existing_urls,
        )
        for item in parsed
    ]


@router.post("", response_model=SourceResponse, status_code=201)
async def create_source(data: SourceCreate, db: AsyncSession = Depends(get_db)):
    repo = SourceRepository(db)
    payload = data.model_dump()
    existing = await repo.get_one(Source.url == payload["url"])
    if existing:
        raise HTTPException(status_code=409, detail="信源 URL 已存在")
    if payload.get("sort_order") is None:
        max_order = await db.scalar(select(func.max(Source.sort_order)))
        payload["sort_order"] = (max_order or 0) + 10
    source = await repo.create(**payload)
    _invalidate_source_cache()
    return source


@router.get("", response_model=SourceListResponse)
async def list_sources(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    source_type: Optional[str] = None,
    status: Optional[str] = None,
    enabled: Optional[bool] = None,
    keyword: Optional[str] = None,
):
    cache_params = SourceListCacheParams(
        page=page,
        page_size=page_size,
        source_type=source_type,
        status=status,
        enabled=enabled,
        keyword=keyword,
    )
    cached = get_cached_source_list(cache_params, ttl_seconds=settings.READ_CACHE_TTL_SECONDS)
    if cached:
        content, age_seconds = cached
        return Response(
            content=content,
            media_type="application/json",
            headers={
                "X-Sources-Cache": "HIT",
                "X-Sources-Cache-Age-Ms": str(int(age_seconds * 1000)),
            },
        )

    async with async_session() as db:
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
            sort_by="sort_order", sort_order="asc",
        )
    payload = SourceListResponse(items=items, total=total, page=page, page_size=page_size).model_dump()
    content = set_cached_source_list(cache_params, payload)
    return Response(
        content=content,
        media_type="application/json",
        headers={"X-Sources-Cache": "MISS"},
    )


@router.post("/reorder")
async def reorder_sources(data: SourceReorderRequest, db: AsyncSession = Depends(get_db)):
    """Persist source order for one kanban lane or the current ordered subset."""
    unique_ids = list(dict.fromkeys(data.ordered_ids))
    if not unique_ids:
        raise HTTPException(status_code=400, detail="ordered_ids cannot be empty")

    result = await db.execute(select(Source).where(Source.id.in_(unique_ids)))
    sources_by_id = {source.id: source for source in result.scalars().all()}
    missing_ids = [source_id for source_id in unique_ids if source_id not in sources_by_id]
    if missing_ids:
        raise HTTPException(status_code=404, detail=f"Sources not found: {missing_ids}")

    for index, source_id in enumerate(unique_ids):
        sources_by_id[source_id].sort_order = (index + 1) * 10

    await db.flush()
    _invalidate_source_cache()
    return {"message": "信源顺序已保存", "updated": len(unique_ids)}


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
        try:
            feed_url = normalize_source_url_value(outline.get("xmlUrl", ""))
        except ValueError:
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

    _invalidate_source_cache()
    return {
        "created": created, "skipped": skipped, "total": len(outlines),
        "message": f"成功导入 {created} 个源，跳过 {skipped} 个重复。",
    }


@router.post("/preview-batch")
async def preview_source_batch(
    data: SourceBatchImportRequest,
    db: AsyncSession = Depends(get_db),
):
    """Preview JSON/Markdown/OPML source config before importing."""
    items = await _preview_source_batch_items(db, data.content, data.category)
    return {
        "items": items,
        "total": len(items),
        "duplicates": sum(1 for item in items if item.duplicate),
        "importable": sum(1 for item in items if not item.duplicate),
    }


@router.post("/import-batch")
async def import_source_batch(
    data: SourceBatchImportRequest,
    db: AsyncSession = Depends(get_db),
):
    """Import sources from JSON/Markdown/OPML text."""
    items = await _preview_source_batch_items(db, data.content, data.category)
    repo = SourceRepository(db)
    max_order = await db.scalar(select(func.max(Source.sort_order)))
    next_order = (max_order or 0) + 10
    created = skipped = 0

    for item in items:
        if item.duplicate:
            skipped += 1
            continue
        try:
            source_type = SourceType(item.source_type)
        except ValueError:
            source_type = SourceType.RSS
        await repo.create(
            name=item.name,
            url=item.url,
            source_type=source_type,
            category=item.category,
            platform=item.platform,
            weight=data.weight,
            sort_order=next_order,
            enabled=data.enabled,
            status=SourceStatus.ACTIVE if data.enabled else SourceStatus.DISABLED,
        )
        next_order += 10
        created += 1

    _invalidate_source_cache()
    return {
        "created": created,
        "skipped": skipped,
        "total": len(items),
        "message": f"成功导入 {created} 个信源，跳过 {skipped} 个重复。",
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
        payload = data.model_dump(exclude_unset=True)
        await repo.get_by_id_or_raise(source_id, resource_name="Source")
        if "url" in payload:
            existing = await repo.get_one(Source.url == payload["url"])
            if existing and existing.id != source_id:
                raise HTTPException(status_code=409, detail="信源 URL 已存在")
        source = await repo.update(source_id, **payload)
        _invalidate_source_cache()
        return source
    except NotFoundError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.delete("/{source_id}", status_code=204)
async def delete_source(source_id: int, db: AsyncSession = Depends(get_db)):
    repo = SourceRepository(db)
    try:
        await repo.delete(source_id)
        _invalidate_source_cache()
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
    _invalidate_source_cache()
    if source.status == SourceStatus.ERROR or source.sync_error:
        await db.commit()
        raise HTTPException(status_code=502, detail=source.sync_error or "信源同步失败")
    return SyncResultResponse(
        fetched=stats["fetched"], new=stats["new"], duplicates=stats["duplicates"],
        source_info=SourceResponse.model_validate(source),
    )
