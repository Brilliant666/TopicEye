"""
Repository for TopicGroup model operations.
"""

from __future__ import annotations

from sqlalchemy import select

from app.models.topic import TopicGroup
from app.repositories.base import BaseRepository


class TopicRepository(BaseRepository[TopicGroup]):
    """TopicGroup table CRUD + get-or-create helper."""

    model = TopicGroup

    async def get_or_create(self, name: str, **defaults) -> TopicGroup:
        """Return an existing TopicGroup by name, or create one if missing."""
        stmt = select(TopicGroup).where(TopicGroup.name == name)
        result = await self.db.execute(stmt)
        topic = result.scalar_one_or_none()

        if topic is not None:
            return topic

        return await self.create(name=name, **defaults)
