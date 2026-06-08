"""
ContentItem Repository.

Extends BaseRepository with content-specific queries:
  - duplicate detection via content_hash
  - status lifecycle helpers
  - topic-grouped queries
  - bulk status updates
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Any, Optional, Sequence

from sqlalchemy import select, update, func, exists
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.content import ContentItem, ContentStatus
from app.repositories.analysis_queries import latest_analysis_id_subquery
from app.repositories.base import BaseRepository

logger = logging.getLogger(__name__)
ANALYSIS_STALE_MINUTES = 10


@dataclass
class ScoringContentRow:
    """Lightweight content + latest analysis row for scoring diagnostics."""

    id: int
    title: str
    url: str
    source_id: Optional[int]
    source_name: Optional[str]
    category: Optional[str]
    summary: Optional[str]
    tags: Optional[Any]
    is_favorited: bool
    published_at: Optional[datetime]
    crawled_at: datetime
    source_weight_db: int
    ai_summary: Optional[str]
    recommendation: Optional[str]
    recommended_reason: Optional[str]
    analysis_tags: Optional[Any]
    creator_angles: Optional[Any]
    curation_score: Optional[float]
    info_density: Optional[float]
    actionability: Optional[float]
    source_weight: Optional[float]
    creator_score: Optional[float]
    viral_score: Optional[float]
    freshness_score: Optional[float]
    quality_score: Optional[float]
    hot_score: Optional[float]
    risk_score: Optional[float]


class ContentRepo(BaseRepository[ContentItem]):
    model = ContentItem
    filter_fields = {"source_type", "platform", "status", "category"}

    def __init__(self, db: AsyncSession):
        super().__init__(db)

    # ── Lookup helpers ─────────────────────────────────────────────

    async def get_by_url(self, url: str) -> Optional[ContentItem]:
        """Find a content item by its URL."""
        result = await self.db.execute(
            select(self.model).where(self.model.url == url)
        )
        return result.scalar_one_or_none()

    async def get_by_content_hash(self, content_hash: str) -> Optional[ContentItem]:
        """Find a content item by its content hash (duplicate detection)."""
        result = await self.db.execute(
            select(self.model).where(self.model.content_hash == content_hash)
        )
        return result.scalar_one_or_none()

    async def get_with_analyses(self, id: int) -> Optional[ContentItem]:
        """Fetch a content item eagerly loaded with its AI analyses."""
        result = await self.db.execute(
            select(self.model)
            .options(selectinload(self.model.analyses))
            .where(self.model.id == id)
        )
        return result.scalar_one_or_none()

    # ── Status lifecycle ───────────────────────────────────────────

    async def get_by_status(
        self,
        status: ContentStatus,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[ContentItem]:
        """Fetch items with a given status, ordered by creation time."""
        result = await self.db.execute(
            select(self.model)
            .where(self.model.status == status)
            .order_by(self.model.created_at.asc())
            .offset(offset)
            .limit(limit)
        )
        return result.scalars().all()

    async def list_pending_for_analysis(
        self,
        *,
        limit: int = 20,
        hours: Optional[int] = None,
    ) -> Sequence[ContentItem]:
        """Fetch recent pending or stale analyzing items for analysis, newest collected first."""
        stale_cutoff = datetime.utcnow() - timedelta(minutes=ANALYSIS_STALE_MINUTES)
        stmt = (
            select(self.model)
            .where(
                (self.model.status == ContentStatus.PENDING)
                | (
                    (self.model.status == ContentStatus.ANALYZING)
                    & (self.model.updated_at <= stale_cutoff)
                )
            )
            .order_by(self.model.crawled_at.desc(), self.model.created_at.desc())
            .limit(limit)
        )
        if hours is not None:
            stmt = stmt.where(self.model.crawled_at >= datetime.utcnow() - timedelta(hours=hours))
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def update_status(self, id: int, status: ContentStatus) -> ContentItem:
        """Transition a single item to a new status."""
        return await self.update(id, status=status)

    async def bulk_update_status(
        self,
        ids: list[int],
        status: ContentStatus,
    ) -> int:
        """
        Bulk-update status for multiple items.
        Returns the number of rows matched.
        """
        stmt = (
            update(self.model)
            .where(self.model.id.in_(ids))
            .values(status=status, updated_at=datetime.utcnow())
        )
        result = await self.db.execute(stmt)
        await self.db.flush()
        return result.rowcount

    # ── Topic & duplicate helpers ──────────────────────────────────

    async def get_by_topic(
        self,
        topic_id: int,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[Sequence[ContentItem], int]:
        """Paginated listing of items belonging to a topic group."""
        return await self.list_paginated(
            page=page,
            page_size=page_size,
            filters={"topic_id": topic_id},
            sort_by="published_at",
            sort_order="desc",
        )

    async def get_duplicates_of(self, canonical_id: int) -> Sequence[ContentItem]:
        """Fetch all items marked as duplicates of a canonical item."""
        result = await self.db.execute(
            select(self.model)
            .where(self.model.duplicate_of == canonical_id)
            .order_by(self.model.similarity_score.desc())
        )
        return result.scalars().all()

    async def mark_as_duplicate(
        self,
        item_id: int,
        canonical_id: int,
        similarity_score: float = 0.0,
    ) -> ContentItem:
        """Mark an item as a duplicate of another item."""
        return await self.update(
            item_id,
            duplicate_of=canonical_id,
            similarity_score=similarity_score,
        )

    async def assign_topic(
        self,
        item_id: int,
        topic_id: int,
    ) -> ContentItem:
        """Assign a content item to a topic group."""
        return await self.update(item_id, topic_id=topic_id)

    async def unassign_topic(self, item_id: int) -> ContentItem:
        """Remove a content item from its topic group."""
        return await self.update(item_id, topic_id=None)

    # ── Stats / counts ─────────────────────────────────────────────

    async def count_by_status(self) -> dict[ContentStatus, int]:
        """Return a breakdown of item counts per status."""
        stmt = (
            select(self.model.status, func.count())
            .group_by(self.model.status)
        )
        result = await self.db.execute(stmt)
        return {status: count for status, count in result.all()}

    async def count_by_category(self) -> dict[str, int]:
        """Return a breakdown of item counts per category."""
        stmt = (
            select(self.model.category, func.count())
            .where(self.model.category.isnot(None))
            .group_by(self.model.category)
        )
        result = await self.db.execute(stmt)
        return {category: count for category, count in result.all()}

    async def delete_old_pending(self, cutoff_days: int = 90) -> int:
        """删除超过指定天数的 pending 状态内容。返回删除数量。"""
        from sqlalchemy import delete as sa_delete
        cutoff = datetime.utcnow() - timedelta(days=cutoff_days)
        stmt = (
            sa_delete(self.model)
            .where(self.model.status == ContentStatus.PENDING)
            .where(self.model.created_at < cutoff)
        )
        result = await self.db.execute(stmt)
        await self.db.flush()
        return result.rowcount

    # ── Eager-loaded paginated listing ────────────────────────────

    async def list_paginated_with_analyses(
        self,
        page: int = 1,
        page_size: int = 20,
        filters: Optional[dict] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        exclude_ids: Optional[set] = None,
        exclude_source_types: Optional[set[str]] = None,
        time_cutoff: Optional[datetime] = None,
    ) -> tuple[Sequence[ContentItem], int]:
        """Like list_paginated but eager-loads analyses relation."""
        stmt = select(self.model).options(selectinload(self.model.analyses))
        count_stmt = select(func.count()).select_from(self.model)

        if filters:
            for field, value in filters.items():
                if value is None:
                    continue
                col = getattr(self.model, field, None)
                if col is None:
                    continue
                if isinstance(value, str) and ("%" in value or "_" in value):
                    stmt = stmt.where(col.ilike(value))
                    count_stmt = count_stmt.where(col.ilike(value))
                else:
                    stmt = stmt.where(col == value)
                    count_stmt = count_stmt.where(col == value)

        # Exclude ignored item IDs
        if exclude_ids:
            stmt = stmt.where(self.model.id.notin_(exclude_ids))
            count_stmt = count_stmt.where(self.model.id.notin_(exclude_ids))
        if exclude_source_types:
            stmt = stmt.where(self.model.source_type.notin_(exclude_source_types))
            count_stmt = count_stmt.where(self.model.source_type.notin_(exclude_source_types))

        # Time range filter
        if time_cutoff:
            stmt = stmt.where(self.model.crawled_at >= time_cutoff)
            count_stmt = count_stmt.where(self.model.crawled_at >= time_cutoff)

        total_result = await self.db.execute(count_stmt)
        total = total_result.scalar() or 0

        sort_col = getattr(self.model, sort_by, self.model.created_at)
        stmt = stmt.order_by(
            sort_col.desc() if sort_order == "desc" else sort_col.asc()
        )

        offset = (page - 1) * page_size
        stmt = stmt.offset(offset).limit(page_size)

        result = await self.db.execute(stmt)
        items = result.scalars().unique().all()
        return items, total

    # ── Detail with metrics + analyses ────────────────────────────

    async def get_detail(self, id: int) -> Optional[ContentItem]:
        """Fetch a content item eagerly loaded with metrics and analyses."""
        result = await self.db.execute(
            select(self.model)
            .options(selectinload(self.model.metrics))
            .options(selectinload(self.model.analyses))
            .where(self.model.id == id)
        )
        return result.scalar_one_or_none()

    # ── Favorites listing ─────────────────────────────────────────

    async def list_favorites(
        self, page: int = 1, page_size: int = 20,
    ) -> tuple[Sequence[ContentItem], int]:
        """Paginated listing of favorited items with analyses."""
        return await self.list_paginated_with_analyses(
            page=page,
            page_size=page_size,
            filters={"is_favorited": True},
            sort_by="updated_at",
            sort_order="desc",
        )

    # ── Today picks candidates (SQLite fallback) ─────────────────

    async def list_for_today_picks(
        self,
        hours: int = 48,
        category: Optional[str] = None,
    ) -> Sequence[ContentItem]:
        """Fetch items with analyses + source for today-picks scoring."""
        from app.models.analysis import AiAnalysis
        from datetime import datetime as dt, timedelta

        cutoff = dt.utcnow() - timedelta(hours=hours)
        latest_analysis_id = self._latest_analysis_id_subquery(AiAnalysis)
        stmt = (
            select(self.model)
            .options(
                selectinload(self.model.analyses),
                selectinload(self.model.source),
            )
            .join(AiAnalysis, AiAnalysis.id == latest_analysis_id)
            .where(self.model.crawled_at >= cutoff)
            .where(AiAnalysis.risk_score <= 70)
        )
        if category:
            stmt = stmt.where(self.model.category == category)
        result = await self.db.execute(stmt)
        return result.scalars().unique().all()

    async def list_for_report_window(
        self,
        *,
        window_start: datetime,
        window_end: datetime,
        category: Optional[str] = None,
    ) -> Sequence[ContentItem]:
        """Fetch analyzed items in a precise report window for daily report snapshots."""
        from app.models.analysis import AiAnalysis

        latest_analysis_id = self._latest_analysis_id_subquery(AiAnalysis)
        stmt = (
            select(self.model)
            .options(
                selectinload(self.model.analyses),
                selectinload(self.model.source),
            )
            .join(AiAnalysis, AiAnalysis.id == latest_analysis_id)
            .where(self.model.crawled_at >= window_start)
            .where(self.model.crawled_at <= window_end)
            .where(AiAnalysis.risk_score <= 70)
            .where(AiAnalysis.curation_score.isnot(None))
        )
        if category:
            stmt = stmt.where(self.model.category == category)
        result = await self.db.execute(stmt)
        return result.scalars().unique().all()

    # ── Scoring candidates (generic, reusable) ─────────────────────────

    async def list_for_scoring(
        self,
        *,
        filters: Optional[dict] = None,
        exclude_ids: Optional[set] = None,
        exclude_source_types: Optional[set[str]] = None,
        time_cutoff: Optional[datetime] = None,
        limit: int = 500,
    ) -> tuple[Sequence[ContentItem], int]:
        """
        Fetch ANALYZED items with analyses + source for scoring pipeline.
        Applies all standard filters (source_type, platform, category, keyword, etc.).
        Returns (items, total_count) where total is the count of all ANALYZED items
        matching filters (for correct pagination total).
        """
        from sqlalchemy import func, select
        from app.models.analysis import AiAnalysis

        latest_analysis_id = self._latest_analysis_id_subquery(AiAnalysis)

        # Count query — all analyzed matching filters
        count_stmt = select(func.count(self.model.id)).join(
            AiAnalysis, AiAnalysis.id == latest_analysis_id
        ).where(self.model.status == ContentStatus.ANALYZED)

        # Data query — eager-load analyses + source
        data_stmt = (
            select(self.model)
            .options(
                selectinload(self.model.analyses),
                selectinload(self.model.source),
            )
            .join(AiAnalysis, AiAnalysis.id == latest_analysis_id)
            .where(self.model.status == ContentStatus.ANALYZED)
        )

        for field, value in (filters or {}).items():
            if value is None:
                continue
            col = getattr(self.model, field, None)
            if col is None:
                continue
            if isinstance(value, str) and ("%" in value or "_" in value):
                count_stmt = count_stmt.where(col.ilike(value))
                data_stmt = data_stmt.where(col.ilike(value))
            else:
                count_stmt = count_stmt.where(col == value)
                data_stmt = data_stmt.where(col == value)

        if exclude_ids:
            count_stmt = count_stmt.where(self.model.id.notin_(exclude_ids))
            data_stmt = data_stmt.where(self.model.id.notin_(exclude_ids))
        if exclude_source_types:
            count_stmt = count_stmt.where(self.model.source_type.notin_(exclude_source_types))
            data_stmt = data_stmt.where(self.model.source_type.notin_(exclude_source_types))
        if time_cutoff:
            count_stmt = count_stmt.where(self.model.crawled_at >= time_cutoff)
            data_stmt = data_stmt.where(self.model.crawled_at >= time_cutoff)

        total_result = await self.db.execute(count_stmt)
        total = total_result.scalar() or 0

        data_stmt = data_stmt.order_by(self.model.crawled_at.desc()).limit(limit)
        result = await self.db.execute(data_stmt)
        items = result.scalars().unique().all()
        return items, total

    async def count_for_scoring(
        self,
        *,
        exclude_ids: Optional[set] = None,
        exclude_source_types: Optional[set[str]] = None,
        time_cutoff: Optional[datetime] = None,
    ) -> int:
        """Count items with analysis rows eligible for scoring diagnostics."""
        from app.models.analysis import AiAnalysis

        stmt = select(func.count(self.model.id)).where(
            exists().where(AiAnalysis.content_id == self.model.id),
        )

        if exclude_ids:
            stmt = stmt.where(self.model.id.notin_(exclude_ids))
        if exclude_source_types:
            stmt = stmt.where(self.model.source_type.notin_(exclude_source_types))
        if time_cutoff:
            stmt = stmt.where(self.model.crawled_at >= time_cutoff)

        result = await self.db.execute(stmt)
        return int(result.scalar() or 0)

    async def count_collected_for_scoring_window(
        self,
        *,
        exclude_ids: Optional[set] = None,
        exclude_source_types: Optional[set[str]] = None,
        time_cutoff: Optional[datetime] = None,
    ) -> int:
        """Count collected content in the same source scope as scoring diagnostics."""
        stmt = select(func.count(self.model.id))

        if exclude_ids:
            stmt = stmt.where(self.model.id.notin_(exclude_ids))
        if exclude_source_types:
            stmt = stmt.where(self.model.source_type.notin_(exclude_source_types))
        if time_cutoff:
            stmt = stmt.where(self.model.crawled_at >= time_cutoff)

        result = await self.db.execute(stmt)
        return int(result.scalar() or 0)

    async def list_scoring_rows(
        self,
        *,
        exclude_ids: Optional[set] = None,
        exclude_source_types: Optional[set[str]] = None,
        time_cutoff: Optional[datetime] = None,
        limit: int = 500,
    ) -> list[ScoringContentRow]:
        """Fetch only columns needed by the scoring debug payload."""
        from app.models.analysis import AiAnalysis
        from app.models.source import Source

        latest_analysis_id = self._latest_analysis_id_subquery(AiAnalysis)

        stmt = (
            select(
                self.model.id,
                self.model.title,
                self.model.url,
                self.model.source_id,
                self.model.source_name,
                self.model.category,
                self.model.summary,
                self.model.tags,
                self.model.is_favorited,
                self.model.published_at,
                self.model.crawled_at,
                func.coalesce(Source.weight, 3).label("source_weight_db"),
                AiAnalysis.summary.label("ai_summary"),
                AiAnalysis.recommendation,
                AiAnalysis.recommended_reason,
                AiAnalysis.tags.label("analysis_tags"),
                AiAnalysis.creator_angles,
                AiAnalysis.curation_score,
                AiAnalysis.info_density,
                AiAnalysis.actionability,
                AiAnalysis.source_weight,
                AiAnalysis.creator_score,
                AiAnalysis.viral_score,
                AiAnalysis.freshness_score,
                AiAnalysis.quality_score,
                AiAnalysis.hot_score,
                AiAnalysis.risk_score,
            )
            .select_from(self.model)
            .join(AiAnalysis, AiAnalysis.id == latest_analysis_id)
            .outerjoin(Source, Source.id == self.model.source_id)
        )

        if exclude_ids:
            stmt = stmt.where(self.model.id.notin_(exclude_ids))
        if exclude_source_types:
            stmt = stmt.where(self.model.source_type.notin_(exclude_source_types))
        if time_cutoff:
            stmt = stmt.where(self.model.crawled_at >= time_cutoff)

        stmt = stmt.order_by(self.model.crawled_at.desc()).limit(limit)
        result = await self.db.execute(stmt)
        return [ScoringContentRow(**row._mapping) for row in result.all()]

    def _latest_analysis_id_subquery(self, analysis_model):
        """Return a correlated subquery for the latest analysis row per content item."""
        return latest_analysis_id_subquery(self.model, analysis_model)

    # ── Recent items ───────────────────────────────────────────────

    async def get_recent(
        self,
        *,
        limit: int = 20,
        status: Optional[ContentStatus] = None,
        source_type: Optional[str] = None,
        platform: Optional[str] = None,
    ) -> Sequence[ContentItem]:
        """Fetch the most recent items, optionally filtered."""
        stmt = select(self.model).order_by(self.model.created_at.desc())

        if status is not None:
            stmt = stmt.where(self.model.status == status)
        if source_type is not None:
            stmt = stmt.where(self.model.source_type == source_type)
        if platform is not None:
            stmt = stmt.where(self.model.platform == platform)

        stmt = stmt.limit(limit)
        result = await self.db.execute(stmt)
        return result.scalars().all()
