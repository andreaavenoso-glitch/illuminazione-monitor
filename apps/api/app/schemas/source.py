from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SourceBase(BaseModel):
    name: str
    source_type: str = Field(description="official | eproc_portal | albo | press | other")
    platform_type: str | None = None
    base_url: str
    sector_scope: str | None = None
    priority: str = "B"
    frequency: str = "daily"
    reliability_score: Decimal = Decimal(0)
    productivity_score: Decimal = Decimal(0)
    publication_model: str | None = None
    source_priority_rank: int = 999
    active: bool = True


class SourceCreate(SourceBase):
    pass


class SourceUpdate(BaseModel):
    name: str | None = None
    source_type: str | None = None
    platform_type: str | None = None
    base_url: str | None = None
    sector_scope: str | None = None
    priority: str | None = None
    frequency: str | None = None
    reliability_score: Decimal | None = None
    productivity_score: Decimal | None = None
    publication_model: str | None = None
    source_priority_rank: int | None = None
    active: bool | None = None


class SourceRead(SourceBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    last_checked_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
