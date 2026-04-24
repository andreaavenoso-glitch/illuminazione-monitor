from datetime import date

from app.core.database import get_session
from app.repositories.report_repository import ReportRepository
from app.schemas.report import DailyReportRead, DailyReportSummary
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.get("/latest", response_model=DailyReportRead)
async def latest_report(session: AsyncSession = Depends(get_session)) -> DailyReportRead:
    repo = ReportRepository(session)
    report = await repo.latest()
    if report is None:
        raise HTTPException(status_code=404, detail="No reports available yet")
    return DailyReportRead.model_validate(report)


@router.get("/history", response_model=list[DailyReportSummary])
async def report_history(
    limit: int = 30,
    session: AsyncSession = Depends(get_session),
) -> list[DailyReportSummary]:
    repo = ReportRepository(session)
    items = await repo.list_recent(limit=limit)
    return [DailyReportSummary.model_validate(i) for i in items]


@router.get("/daily/{report_date}", response_model=DailyReportRead)
async def report_by_date(
    report_date: date,
    session: AsyncSession = Depends(get_session),
) -> DailyReportRead:
    repo = ReportRepository(session)
    report = await repo.get_by_date(report_date)
    if report is None:
        raise HTTPException(status_code=404, detail=f"No report for {report_date}")
    return DailyReportRead.model_validate(report)
