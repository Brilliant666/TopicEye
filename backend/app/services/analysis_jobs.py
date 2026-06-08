from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from app.core.config import settings


MAX_TRACKED_ANALYSIS_JOBS = 100


@dataclass
class AnalysisJob:
    job_id: str
    content_ids: list[int]
    skipped_inflight_ids: list[int] = field(default_factory=list)
    status: str = "QUEUED"
    queued_at: datetime = field(default_factory=datetime.utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    analyzed_ids: list[int] = field(default_factory=list)
    failed_ids: list[int] = field(default_factory=list)
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        analyzed = set(self.analyzed_ids)
        failed = set(self.failed_ids)
        return {
            "job_id": self.job_id,
            "status": self.status,
            "content_ids": self.content_ids,
            "queued_ids": self.content_ids,
            "skipped_inflight_ids": self.skipped_inflight_ids,
            "analyzed_ids": self.analyzed_ids,
            "failed_ids": self.failed_ids,
            "pending_ids": [
                content_id
                for content_id in self.content_ids
                if content_id not in analyzed and content_id not in failed
            ],
            "count": len(self.content_ids),
            "queued_count": len(self.content_ids),
            "skipped_inflight_count": len(self.skipped_inflight_ids),
            "analyzed_count": len(self.analyzed_ids),
            "failed_count": len(self.failed_ids),
            "queued_at": self.queued_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "error_message": self.error_message,
        }


_jobs: OrderedDict[str, AnalysisJob] = OrderedDict()
_active_content_ids: set[int] = set()
_lock = asyncio.Lock()


def _prune_jobs() -> None:
    while len(_jobs) > MAX_TRACKED_ANALYSIS_JOBS:
        _jobs.popitem(last=False)


def _release_expired_active_ids(now: datetime) -> None:
    try:
        ttl_seconds = max(60, int(settings.ANALYSIS_JOB_INFLIGHT_TTL_SECONDS))
    except (TypeError, ValueError):
        ttl_seconds = 900

    expired_ids: set[int] = set()
    for job in _jobs.values():
        if job.status not in {"QUEUED", "RUNNING"}:
            continue
        anchor = job.started_at or job.queued_at
        if (now - anchor).total_seconds() > ttl_seconds:
            job.status = "EXPIRED"
            job.finished_at = now
            job.error_message = "Analysis job expired before reporting completion"
            expired_ids.update(job.content_ids)
    _active_content_ids.difference_update(expired_ids)


async def create_analysis_job(content_ids: list[int]) -> AnalysisJob:
    """Register an analysis background job and deduplicate in-flight content IDs."""
    unique_ids = list(dict.fromkeys(content_ids))
    async with _lock:
        _release_expired_active_ids(datetime.utcnow())
        queued_ids = [content_id for content_id in unique_ids if content_id not in _active_content_ids]
        skipped_ids = [content_id for content_id in unique_ids if content_id in _active_content_ids]
        job = AnalysisJob(
            job_id=uuid4().hex,
            content_ids=queued_ids,
            skipped_inflight_ids=skipped_ids,
            status="QUEUED" if queued_ids else "SKIPPED",
            finished_at=None if queued_ids else datetime.utcnow(),
        )
        _jobs[job.job_id] = job
        _active_content_ids.update(queued_ids)
        _prune_jobs()
        return job


async def mark_analysis_job_running(job_id: str) -> None:
    async with _lock:
        job = _jobs.get(job_id)
        if job and job.status == "QUEUED":
            job.status = "RUNNING"
            job.started_at = datetime.utcnow()


async def finish_analysis_job(
    job_id: str,
    *,
    analyzed_ids: list[int] | None = None,
    failed_ids: list[int] | None = None,
    error_message: str | None = None,
) -> None:
    async with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        analyzed = list(dict.fromkeys(analyzed_ids or []))
        failed = list(dict.fromkeys(failed_ids or []))
        job.analyzed_ids = analyzed
        job.failed_ids = failed
        job.error_message = error_message[:1000] if error_message else None
        job.finished_at = datetime.utcnow()
        if error_message:
            job.status = "FAILED"
        elif failed and analyzed:
            job.status = "PARTIAL"
        elif failed:
            job.status = "FAILED"
        else:
            job.status = "SUCCESS"
        _active_content_ids.difference_update(job.content_ids)


async def get_analysis_job(job_id: str) -> dict[str, Any] | None:
    async with _lock:
        job = _jobs.get(job_id)
        return job.to_dict() if job else None


async def reset_analysis_jobs() -> None:
    """Clear in-memory job state for tests and process-local maintenance."""
    async with _lock:
        _jobs.clear()
        _active_content_ids.clear()
