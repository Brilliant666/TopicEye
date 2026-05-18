"""
Daily Report API endpoints.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.daily_report import DailyReport
from app.schemas.daily_report import DailyReportResponse, DailyReportListResponse
from app.services.daily_report import generate_daily_report

router = APIRouter(prefix="/daily-reports", tags=["daily-reports"])


@router.get("/today", response_model=DailyReportResponse)
async def get_today_report(db: AsyncSession = Depends(get_db)):
    """Get or generate today's daily report."""
    report = await generate_daily_report(db)
    return report


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
        .order_by(DailyReport.report_date.desc())
        .limit(limit)
    )
    items = result.scalars().all()

    return {"items": items, "total": total}


@router.post("/generate", response_model=DailyReportResponse)
async def trigger_generate(db: AsyncSession = Depends(get_db)):
    """Force regenerate today's daily report."""
    from app.models.daily_report import DailyReport
    from datetime import date

    today = date.today().isoformat()
    # Delete existing today's report to force regeneration
    existing = await db.execute(
        select(DailyReport).where(DailyReport.report_date == today)
    )
    report = existing.scalar_one_or_none()
    if report:
        report.status = "PENDING"
        await db.flush()

    report = await generate_daily_report(db)
    return report
