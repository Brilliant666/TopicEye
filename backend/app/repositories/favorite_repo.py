from __future__ import annotations

from datetime import datetime
from typing import Optional, Sequence, Union

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem
from app.models.favorite import FavoriteItem, FavoriteStatus, FavoriteTargetType
from app.schemas.favorite import FavoriteCreate, FavoriteUpdate


class FavoriteRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def make_target_key(
        target_type: Union[FavoriteTargetType, str],
        *,
        target_id: Optional[int] = None,
        target_key: Optional[str] = None,
    ) -> str:
        if target_key:
            return target_key
        if target_id is None:
            raise ValueError("target_id or target_key is required")
        return str(target_id)

    async def get_by_target(
        self,
        target_type: Union[FavoriteTargetType, str],
        target_key: str,
    ) -> Optional[FavoriteItem]:
        result = await self.db.execute(
            select(FavoriteItem).where(
                FavoriteItem.target_type == target_type,
                FavoriteItem.target_key == target_key,
            )
        )
        return result.scalar_one_or_none()

    async def upsert(self, data: FavoriteCreate) -> FavoriteItem:
        target_key = self.make_target_key(
            data.target_type,
            target_id=data.target_id,
            target_key=data.target_key,
        )
        payload = data.model_dump()
        payload["target_key"] = target_key

        if data.target_type == FavoriteTargetType.CONTENT:
            payload = await self._merge_content_snapshot(payload)

        if not payload.get("title"):
            raise ValueError("title is required when target cannot be resolved")

        existing = await self.get_by_target(data.target_type, target_key)
        if existing:
            for key, value in payload.items():
                if value is not None and hasattr(existing, key):
                    setattr(existing, key, value)
            existing.updated_at = datetime.utcnow()
            await self.db.flush()
            await self.db.refresh(existing)
            return existing

        item = FavoriteItem(**payload)
        self.db.add(item)
        await self.db.flush()
        await self.db.refresh(item)
        return item

    async def create_from_content(self, content_id: int) -> FavoriteItem:
        data = FavoriteCreate(target_type=FavoriteTargetType.CONTENT, target_id=content_id)
        return await self.upsert(data)

    async def remove_by_content(self, content_id: int) -> bool:
        return await self.delete_by_target(
            FavoriteTargetType.CONTENT,
            self.make_target_key(FavoriteTargetType.CONTENT, target_id=content_id),
        )

    async def delete_by_target(self, target_type: Union[FavoriteTargetType, str], target_key: str) -> bool:
        result = await self.db.execute(
            delete(FavoriteItem).where(
                FavoriteItem.target_type == target_type,
                FavoriteItem.target_key == target_key,
            )
        )
        await self.db.flush()
        return bool(result.rowcount)

    async def delete(self, favorite_id: int) -> bool:
        result = await self.db.execute(delete(FavoriteItem).where(FavoriteItem.id == favorite_id))
        await self.db.flush()
        return bool(result.rowcount)

    async def update(self, favorite_id: int, data: FavoriteUpdate) -> Optional[FavoriteItem]:
        item = await self.get_by_id(favorite_id)
        if not item:
            return None
        payload = data.model_dump(exclude_unset=True)
        for key, value in payload.items():
            if hasattr(item, key):
                setattr(item, key, value)
        item.updated_at = datetime.utcnow()
        await self.db.flush()
        await self.db.refresh(item)
        return item

    async def get_by_id(self, favorite_id: int) -> Optional[FavoriteItem]:
        result = await self.db.execute(select(FavoriteItem).where(FavoriteItem.id == favorite_id))
        return result.scalar_one_or_none()

    async def list_paginated(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        target_type: Optional[FavoriteTargetType] = None,
        status: Optional[FavoriteStatus] = None,
        keyword: Optional[str] = None,
    ) -> tuple[Sequence[FavoriteItem], int]:
        stmt = select(FavoriteItem)
        count_stmt = select(func.count()).select_from(FavoriteItem)

        if target_type:
            stmt = stmt.where(FavoriteItem.target_type == target_type)
            count_stmt = count_stmt.where(FavoriteItem.target_type == target_type)
        if status:
            stmt = stmt.where(FavoriteItem.status == status)
            count_stmt = count_stmt.where(FavoriteItem.status == status)
        if keyword:
            pattern = f"%{keyword}%"
            stmt = stmt.where(FavoriteItem.title.ilike(pattern))
            count_stmt = count_stmt.where(FavoriteItem.title.ilike(pattern))

        total_result = await self.db.execute(count_stmt)
        total = int(total_result.scalar() or 0)

        result = await self.db.execute(
            stmt.order_by(FavoriteItem.created_at.desc(), FavoriteItem.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return result.scalars().all(), total

    async def state_for_targets(
        self,
        target_type: FavoriteTargetType,
        *,
        target_ids: Optional[list[int]] = None,
        target_keys: Optional[list[str]] = None,
    ) -> list[dict]:
        keys = list(target_keys or [])
        keys.extend(self.make_target_key(target_type, target_id=target_id) for target_id in target_ids or [])
        keys = list(dict.fromkeys(keys))
        if not keys:
            return []

        result = await self.db.execute(
            select(FavoriteItem).where(
                FavoriteItem.target_type == target_type,
                FavoriteItem.target_key.in_(keys),
            )
        )
        by_key = {item.target_key: item for item in result.scalars().all()}
        return [
            {
                "target_key": key,
                "is_favorited": key in by_key,
                "favorite_id": by_key[key].id if key in by_key else None,
            }
            for key in keys
        ]

    async def _merge_content_snapshot(self, payload: dict) -> dict:
        content_id = payload.get("target_id")
        if content_id is None:
            return payload

        result = await self.db.execute(select(ContentItem).where(ContentItem.id == content_id))
        content = result.scalar_one_or_none()
        if not content:
            raise LookupError("Content not found")

        if not payload.get("title"):
            payload["title"] = content.title
        if not payload.get("url"):
            payload["url"] = content.url
        if not payload.get("cover_url"):
            payload["cover_url"] = content.cover_url
        if not payload.get("source_name"):
            payload["source_name"] = content.source_name
        if not payload.get("snapshot"):
            payload["snapshot"] = {
            "content_id": content.id,
            "category": content.category,
            "source_type": content.source_type,
            "platform": content.platform,
            "author": content.author,
            "published_at": content.published_at.isoformat() if content.published_at else None,
            "crawled_at": content.crawled_at.isoformat() if content.crawled_at else None,
            "summary": content.summary,
            }
        return payload
