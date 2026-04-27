from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class WatchlistItemBase(BaseModel):
    entity_id: UUID | None = None
    source_id: UUID | None = None
    url_gare: str | None = None
    url_esiti: str | None = None
    url_albo: str | None = None
    url_trasparenza: str | None = None
    url_determine: str | None = None
    frequency: str = "daily"
    priority: str = "B"
    reliability_score: Decimal = Decimal(0)
    productivity_score: Decimal = Decimal(0)
    publication_model: str | None = None
    active: bool = True


class WatchlistItemCreate(WatchlistItemBase):
    pass


class WatchlistItemUpdate(BaseModel):
    entity_id: UUID | None = None
    source_id: UUID | None = None
    url_gare: str | None = None
    url_esiti: str | None = None
    url_albo: str | None = None
    url_trasparenza: str | None = None
    url_determine: str | None = None
    frequency: str | None = None
    priority: str | None = None
    reliability_score: Decimal | None = None
    productivity_score: Decimal | None = None
    publication_model: str | None = None
    active: bool | None = None


class WatchlistItemRead(WatchlistItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    last_scan_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
