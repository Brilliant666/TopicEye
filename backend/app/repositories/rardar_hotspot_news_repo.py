"""Persistence boundary for the Rardar Hotspot News MVP."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem
from app.models.source import Source


class RardarHotspotNewsRepository:
    """Keep API/services independent from ad-hoc ORM queries."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_source(self, *, platform: str, feed_url: str) -> Source | None:
        result = await self.db.execute(
            select(Source).where(
                Source.owner_user_id.is_(None),
                Source.scope == "system",
                Source.platform == platform,
                Source.url == feed_url,
            )
        )
        return result.scalar_one_or_none()

    async def list_sources(self, *, platform: str, feed_urls: Sequence[str]) -> list[Source]:
        if not feed_urls:
            return []
        result = await self.db.execute(
            select(Source)
            .where(
                Source.owner_user_id.is_(None),
                Source.scope == "system",
                Source.platform == platform,
                Source.url.in_(feed_urls),
            )
            .order_by(Source.sort_order.asc(), Source.id.asc())
        )
        return list(result.scalars().all())

    async def list_items(self, *, source_ids: Sequence[int]) -> list[ContentItem]:
        if not source_ids:
            return []
        result = await self.db.execute(
            select(ContentItem)
            .where(ContentItem.source_id.in_(source_ids))
            .order_by(ContentItem.crawled_at.desc(), ContentItem.id.desc())
        )
        return list(result.scalars().all())

    async def count_items(self, *, source_id: int) -> int:
        result = await self.db.execute(select(func.count(ContentItem.id)).where(ContentItem.source_id == source_id))
        return int(result.scalar_one())

    async def list_items_by_urls(
        self,
        *,
        source_ids: Sequence[int],
        urls: Sequence[str],
    ) -> list[ContentItem]:
        if not source_ids or not urls:
            return []
        result = await self.db.execute(
            select(ContentItem).where(
                ContentItem.source_id.in_(source_ids),
                ContentItem.url.in_(urls),
            )
        )
        return list(result.scalars().all())
