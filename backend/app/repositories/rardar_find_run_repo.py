"""Short transactions and atomic execution ownership for Find."""

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rardar_find_run import RardarFindRun


class FindRunRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, user_id: int, run_id: str):
        return await self.db.scalar(
            select(RardarFindRun).where(RardarFindRun.user_id == user_id, RardarFindRun.run_id == run_id)
        )

    async def by_key(self, user_id: int, key: str):
        return await self.db.scalar(
            select(RardarFindRun).where(RardarFindRun.user_id == user_id, RardarFindRun.idempotency_key == key)
        )

    async def add(self, **values):
        row = RardarFindRun(**values)
        self.db.add(row)
        await self.db.flush()
        return row

    async def recent(self, user_id: int, limit: int):
        # Deliberately do not load the request, evidence or result JSON columns.
        query = (
            select(
                RardarFindRun.run_id,
                RardarFindRun.status,
                RardarFindRun.stage,
                RardarFindRun.created_at,
                RardarFindRun.updated_at,
                RardarFindRun.requirement_summary,
                RardarFindRun.repository_url,
                RardarFindRun.requests_used,
                RardarFindRun.execution_deadline,
            )
            .where(RardarFindRun.user_id == user_id)
            .order_by(RardarFindRun.created_at.desc(), RardarFindRun.run_id)
            .limit(limit)
        )
        return (await self.db.execute(query)).mappings().all()

    async def claim(self, user_id: int, run_id: str, token: str, deadline: datetime) -> bool:
        result = await self.db.execute(
            update(RardarFindRun)
            .execution_options(synchronize_session=False)
            .where(
                RardarFindRun.run_id == run_id,
                RardarFindRun.user_id == user_id,
                RardarFindRun.status == "created",
            )
            .values(
                status="running",
                stage="planning",
                execution_token=token,
                execution_deadline=deadline,
                updated_at=datetime.now(UTC),
            )
        )
        return result.rowcount == 1

    async def checkpoint(self, run_id: str, token: str, **values) -> bool:
        result = await self.db.execute(
            update(RardarFindRun)
            .execution_options(synchronize_session=False)
            .where(
                RardarFindRun.run_id == run_id,
                RardarFindRun.execution_token == token,
                RardarFindRun.status == "running",
            )
            .values(**values, updated_at=datetime.now(UTC))
        )
        return result.rowcount == 1

    async def reserve(self, run_id: str, token: str, metadata: dict) -> bool:
        result = await self.db.execute(
            update(RardarFindRun)
            .execution_options(synchronize_session=False)
            .where(
                RardarFindRun.run_id == run_id,
                RardarFindRun.execution_token == token,
                RardarFindRun.status == "running",
                RardarFindRun.requests_used < RardarFindRun.request_limit,
                RardarFindRun.execution_deadline > datetime.now(UTC),
            )
            .values(
                requests_used=RardarFindRun.requests_used + 1, audit_metadata=metadata, updated_at=datetime.now(UTC)
            )
        )
        return result.rowcount == 1
