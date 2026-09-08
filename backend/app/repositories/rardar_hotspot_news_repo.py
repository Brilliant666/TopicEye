"""Persistence boundary for the Rardar Hotspot News MVP."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem
from app.models.source import Source, SourceStatus


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

    async def finish_sync(self, *, source_id: int, completed_at: datetime, error: str | None) -> None:
        """Record fetch health without undoing an administrator's concurrent pause."""
        await self.db.execute(
            update(Source)
            .where(Source.id == source_id)
            .values(
                status=case(
                    (
                        or_(Source.enabled.is_(False), Source.status == SourceStatus.DISABLED),
                        SourceStatus.DISABLED.value,
                    ),
                    else_=SourceStatus.ERROR.value if error else SourceStatus.ACTIVE.value,
                ),
                sync_error=error,
                last_sync_at=completed_at,
                updated_at=completed_at,
            )
            .execution_options(synchronize_session=False)
        )

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

    async def list_items_by_ids(self, *, item_ids: Sequence[int]) -> list[ContentItem]:
        if not item_ids:
            return []
        result = await self.db.execute(select(ContentItem).where(ContentItem.id.in_(item_ids)))
        return list(result.scalars().all())
