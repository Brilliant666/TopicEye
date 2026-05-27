"""
Daily Report API endpoints.
"""
from __future__ import annotations

from datetime import date as date_cls, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.daily_report import DailyReport
from app.repositories.daily_report_repo import DailyReportRepository
from app.schemas.daily_report import (
    DailyReportResponse,
    DailyReportListResponse,
    DailyReportDatesResponse,
)
from app.services.daily_report import generate_daily_report, get_latest_today_report

router = APIRouter(prefix="/daily-reports", tags=["daily-reports"])


@router.get("/today", response_model=DailyReportResponse)
async def get_today_report(db: AsyncSession = Depends(get_db)):
    """Get today's latest daily report snapshot, generating one if none exists."""
    report = await get_latest_today_report(db)
    return report


@router.get("/by-date", response_model=DailyReportResponse)
async def get_report_by_date(
    date: str = Query(..., description="Report date in YYYY-MM-DD format"),
    edition: str | None = Query(None, description="Optional edition: snapshot/noon/evening/final/manual"),
    db: AsyncSession = Depends(get_db),
):
    """Fetch final report for a date, or latest snapshot if final does not exist."""
    repo = DailyReportRepository(db)
    report = await repo.get_by_date(date, edition=edition)
    if report is None:
        raise HTTPException(status_code=404, detail=f"No report found for {date}")
    return report


@router.get("/dates", response_model=DailyReportDatesResponse)
async def list_report_dates(db: AsyncSession = Depends(get_db)):
    """List all dates that have reports, newest first."""
    repo = DailyReportRepository(db)
    dates = await repo.get_dates_with_reports()
    return {"dates": dates}


@router.get("", response_model=DailyReportListResponse)
async def list_reports(
    limit: int = 7,
    db: AsyncSession = Depends(get_db),
):
    """List recent daily reports."""
    count_result = await db.execute(
        select(func.count()).select_from(DailyReport)
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        select(DailyReport)
        .order_by(DailyReport.report_date.desc(), DailyReport.cutoff_at.desc())
        .limit(limit)
    )
    items = result.scalars().all()

    return {"items": items, "total": total}


@router.post("/generate", response_model=DailyReportResponse)
async def trigger_generate(db: AsyncSession = Depends(get_db)):
    """Force generate a daily report snapshot for a date/window."""
    report = await generate_daily_report(db, force=True)
    return report


@router.post("/generate-version", response_model=DailyReportResponse)
async def trigger_generate_version(
    target_date: str | None = Query(None, description="Target date in YYYY-MM-DD, defaults to today"),
    edition: str | None = Query(None, description="snapshot/noon/evening/final/manual"),
    cutoff_at: str | None = Query(None, description="ISO datetime cutoff, defaults to now"),
    force: bool = Query(True, description="Regenerate even if this exact version exists"),
    db: AsyncSession = Depends(get_db),
):
    """Generate a specific daily report version/window."""
    parsed_date = date_cls.fromisoformat(target_date) if target_date else None
    parsed_cutoff = datetime.fromisoformat(cutoff_at) if cutoff_at else None
    report = await generate_daily_report(
        db,
        target_date=parsed_date,
        edition=edition,
        cutoff_at=parsed_cutoff,
        force=force,
    )
    return report
