from datetime import date

from shared_models import DailyReport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class ReportRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_date(self, report_date: date) -> DailyReport | None:
        stmt = select(DailyReport).where(DailyReport.report_date == report_date)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def latest(self) -> DailyReport | None:
        stmt = select(DailyReport).order_by(DailyReport.report_date.desc()).limit(1)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_recent(self, *, limit: int = 30) -> list[DailyReport]:
        stmt = select(DailyReport).order_by(DailyReport.report_date.desc()).limit(limit)
        return list((await self.session.execute(stmt)).scalars().all())

    async def upsert(
        self,
        *,
        report_date: date,
        report_json: dict,
        totals: dict[str, int],
    ) -> DailyReport:
        existing = await self.get_by_date(report_date)
        if existing is None:
            existing = DailyReport(
                report_date=report_date,
                report_json=report_json,
                total_new=totals.get("total_new", 0),
                total_updates=totals.get("total_updates", 0),
                total_pregara=totals.get("total_pregara", 0),
                total_new_sources=totals.get("total_sources_ok", 0),
            )
            self.session.add(existing)
        else:
            existing.report_json = report_json
            existing.total_new = totals.get("total_new", 0)
            existing.total_updates = totals.get("total_updates", 0)
            existing.total_pregara = totals.get("total_pregara", 0)
            existing.total_new_sources = totals.get("total_sources_ok", 0)
        await self.session.flush()
        return existing
