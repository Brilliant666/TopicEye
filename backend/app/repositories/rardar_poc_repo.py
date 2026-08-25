"""Database access for Rardar POC control-plane state."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rardar_poc import RardarAIRequest, RardarFindProjectJob


class RardarFindProjectJobRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, job: RardarFindProjectJob) -> RardarFindProjectJob:
        self.db.add(job)
        await self.db.flush()
        return job

    async def get(self, job_id: str, *, for_update: bool = False) -> RardarFindProjectJob | None:
        stmt = select(RardarFindProjectJob).where(RardarFindProjectJob.job_id == job_id)
        if for_update:
            stmt = stmt.with_for_update()
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def delete(self, job: RardarFindProjectJob) -> None:
        await self.db.delete(job)
        await self.db.flush()

    async def claim_next(self, *, lease_seconds: int = 30) -> RardarFindProjectJob | None:
        now = datetime.now(UTC)
        stmt = (
            select(RardarFindProjectJob)
            .where(
                RardarFindProjectJob.state.in_(("queued", "deep_analysis")),
                or_(
                    RardarFindProjectJob.lease_id.is_(None),
                    RardarFindProjectJob.lease_expires_at < now,
                ),
            )
            .order_by(RardarFindProjectJob.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        job = (await self.db.execute(stmt)).scalar_one_or_none()
        if job is None:
            return None
        job.lease_id = uuid4().hex
        job.lease_expires_at = now + timedelta(seconds=lease_seconds)
        job.attempt_count += 1
        await self.db.flush()
        return job

    async def diagnostics(self) -> dict:
        rows = await self.db.execute(
            select(RardarFindProjectJob.state, func.count()).group_by(RardarFindProjectJob.state)
        )
        return {state: int(count) for state, count in rows.all()}


class RardarAIRequestRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def add(self, request: RardarAIRequest) -> None:
        self.db.add(request)
        await self.db.flush()

    async def diagnostics(self) -> dict:
        total = await self.db.scalar(select(func.count()).select_from(RardarAIRequest)) or 0
        failed = (
            await self.db.scalar(
                select(func.count())
                .select_from(RardarAIRequest)
                .where(RardarAIRequest.result_state.not_in(("ready", "cache_hit")))
            )
            or 0
        )
        cache_hits = (
            await self.db.scalar(
                select(func.count()).select_from(RardarAIRequest).where(RardarAIRequest.result_state == "cache_hit")
            )
            or 0
        )
        return {"total": int(total), "failed": int(failed), "cacheHits": int(cache_hits)}
