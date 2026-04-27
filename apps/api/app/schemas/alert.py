from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    procurement_record_id: UUID | None
    alert_type: str
    severity: str
    description: str
    is_open: bool
    opened_at: datetime
    closed_at: datetime | None
