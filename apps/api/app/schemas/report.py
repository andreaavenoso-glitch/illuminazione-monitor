from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DailyReportSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    report_date: date
    total_new: int
    total_updates: int
    total_pregara: int
    total_new_sources: int
    generated_at: datetime


class DailyReportRead(DailyReportSummary):
    report_json: dict[str, Any]
